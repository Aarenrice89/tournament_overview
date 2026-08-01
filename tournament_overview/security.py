from ipaddress import ip_address


def get_client_ip(request):
    """Return Caddy's sanitized client address, or the direct peer in development."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        try:
            return str(ip_address(forwarded_for))
        except ValueError:
            return None

    try:
        return str(ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        return None
