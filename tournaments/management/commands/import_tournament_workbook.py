from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tournaments.models import Team, Tournament, TournamentRegistration

SPREADSHEET_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class TournamentWorkbook:
    def __init__(self, path):
        self.workbook = ZipFile(path)
        shared_strings = ElementTree.fromstring(self.workbook.read("xl/sharedStrings.xml"))
        self.shared_strings = [
            "".join(item.itertext()) for item in shared_strings.findall(f"{SPREADSHEET_NAMESPACE}si")
        ]
        self.sheet_paths = self._sheet_paths()

    def _sheet_paths(self):
        relationships = ElementTree.fromstring(self.workbook.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships.findall(f"{PACKAGE_RELATIONSHIP_NAMESPACE}Relationship")
        }
        workbook = ElementTree.fromstring(self.workbook.read("xl/workbook.xml"))
        return {
            sheet.attrib["name"]: f"xl/{relationship_targets[sheet.attrib[f'{RELATIONSHIP_NAMESPACE}id']]}"
            for sheet in workbook.find(f"{SPREADSHEET_NAMESPACE}sheets")
        }

    def detail_sheets(self):
        return (name for name in self.sheet_paths if name.startswith("Detail - "))

    def values(self, sheet_name):
        root = ElementTree.fromstring(self.workbook.read(self.sheet_paths[sheet_name]))
        return {cell.attrib["r"]: self._cell_value(cell) for cell in root.findall(f".//{SPREADSHEET_NAMESPACE}c")}

    def hyperlink(self, sheet_name, cell_reference):
        sheet_path = self.sheet_paths[sheet_name]
        relationship_path = sheet_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
        if relationship_path not in self.workbook.namelist():
            return ""

        root = ElementTree.fromstring(self.workbook.read(sheet_path))
        hyperlink = next(
            (
                item
                for item in root.findall(f".//{SPREADSHEET_NAMESPACE}hyperlink")
                if item.attrib.get("ref") == cell_reference
            ),
            None,
        )
        if hyperlink is None:
            return ""

        relationship_id = hyperlink.attrib.get(f"{RELATIONSHIP_NAMESPACE}id")
        if not relationship_id:
            return hyperlink.attrib.get("location", "")

        relationships = ElementTree.fromstring(self.workbook.read(relationship_path))
        relationship = next(
            (
                item
                for item in relationships.findall(f"{PACKAGE_RELATIONSHIP_NAMESPACE}Relationship")
                if item.attrib["Id"] == relationship_id
            ),
            None,
        )
        return relationship.attrib.get("Target", "") if relationship is not None else ""

    def _cell_value(self, cell):
        if cell.attrib.get("t") == "inlineStr":
            inline_string = cell.find(f"{SPREADSHEET_NAMESPACE}is")
            return "".join(inline_string.itertext()) if inline_string is not None else ""

        value = cell.find(f"{SPREADSHEET_NAMESPACE}v")
        if value is None:
            return ""

        raw_value = value.text or ""
        if cell.attrib.get("t") == "s":
            return self.shared_strings[int(raw_value)]
        return raw_value


class Command(BaseCommand):
    help = "Imports tournament detail sheets and registered teams from an Excel workbook."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default=settings.BASE_DIR / "Copy 2026-2027 Tournament Chart.xlsx",
            type=Path,
        )

    def handle(self, *args, **options):
        path = options["path"]
        if not path.is_file():
            raise CommandError(f"Workbook not found: {path}")

        workbook = TournamentWorkbook(path)
        imported_tournaments = 0
        imported_registrations = 0
        warnings = []

        with transaction.atomic():
            for sheet_name in workbook.detail_sheets():
                values = workbook.values(sheet_name)
                tournament, created, sheet_warnings = self._import_tournament(workbook, sheet_name, values)
                warnings.extend(sheet_warnings)
                imported_tournaments += int(created)
                imported_registrations += self._import_registrations(tournament, values)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {imported_tournaments} tournaments and {imported_registrations} tournament registrations."
            )
        )
        for warning in warnings:
            self.stdout.write(self.style.WARNING(warning))

    def _import_tournament(self, workbook, sheet_name, values):
        warnings = []
        name = values["A2"].strip()
        start_date = self._date(values.get("B2"))
        end_date = self._date(values.get("C2"))
        if end_date and start_date and end_date < start_date:
            warnings.append(f"{name}: ignored an end date before the start date.")
            end_date = None

        defaults = {
            "end_date": end_date,
            "location": values.get("D2", "").strip(),
            "registration_opens_date": self._date(values.get("E2")),
            "registration_closes_date": None,
            "registration_link": workbook.hyperlink(sheet_name, "F2"),
            "cost_per_team": self._decimal(values.get("G2"), f"{name}: cost per team", warnings),
            "organizing_company": values.get("J2", "").strip(),
            "team_minimum": self._integer(values.get("K2")),
            "stay_to_play": self._boolean(values.get("I2")),
            "stay_to_play_link": workbook.hyperlink(sheet_name, "L2"),
            "stay_to_play_notes": values.get("M2", "").strip(),
            "coach_hotel": values.get("I5", "").strip(),
            "hotel_location": values.get("K5", "").strip(),
            "number_of_rooms": self._integer(values.get("J5")),
            "cost_per_room": self._decimal(values.get("L5"), f"{name}: cost per room", warnings),
            "coaches_notes": values.get("M5", "").strip(),
            "travel": values.get("I8", "").strip(),
            "flight_number": values.get("J8", "").strip(),
            "number_of_coaches": self._integer(values.get("K8")),
            "travel_notes": values.get("M8", "").strip(),
        }
        tournament, created = Tournament.objects.update_or_create(name=name, start_date=start_date, defaults=defaults)
        tournament.full_clean()
        return tournament, created, warnings

    def _import_registrations(self, tournament, values):
        imported = 0
        for row_number in range(5, 1001):
            name = values.get(f"A{row_number}", "").strip()
            if not name:
                continue

            is_paid = self._boolean(values.get(f"C{row_number}"))
            rosters_entered = self._boolean(values.get(f"D{row_number}"))
            registration, _ = TournamentRegistration.objects.update_or_create(
                tournament=tournament,
                team=Team.objects.get_or_create(name=name)[0],
                defaults={
                    "is_registered": self._boolean(values.get(f"B{row_number}")) or is_paid or rosters_entered,
                    "is_paid": is_paid or rosters_entered,
                    "rosters_entered": rosters_entered,
                },
            )
            registration.full_clean()
            imported += 1
        return imported

    @staticmethod
    def _date(value):
        try:
            return date(1899, 12, 30) + timedelta(days=int(float(value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _integer(value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _boolean(value):
        return str(value).strip().lower() in {"1", "true", "yes", "y"}

    @staticmethod
    def _decimal(value, description, warnings):
        if not value:
            return Decimal("0")
        try:
            return Decimal(str(value))
        except InvalidOperation:
            warnings.append(f"{description}: could not parse {value!r}; stored 0.")
            return Decimal("0")
