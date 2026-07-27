#!/bin/bash
set -eu

if test $# -gt 0; then
    case "$1" in
        -h|--help)
            echo "options:"
            echo "-h, --h           show brief help"
            echo "-s, --service     start service: worker | beat | flower"
            exit 0
            ;;
        -s|--service)
            shift
            if test $# -gt 0; then
                if [[ $1 == "worker" || $1 == "flower" ]]; then
                    service=$1
                    args=""
                elif [ $1 == "beat" ]; then
                    service=$1
                    args=" --scheduler beat.schedulers:DatabaseSchedulerWithCleanup"
                else
                    echo "Valid service options: worker | beat | flower"
                    exit 1
                fi
            else
                echo "No service specified"
                exit 1
            fi
            shift
            ;;
        *)
            echo "Invalid option"
            exit 1
            ;;
    esac
fi

args+=" $@"

cd /app

celery -A yosemite_scraper $service -l info $args