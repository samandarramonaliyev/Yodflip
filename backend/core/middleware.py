"""Small response-header middleware."""

# The scanner uses getUserMedia, so the camera must be allowed for our own origin
# (also when Telegram Web shows the Mini App in an iframe). Everything else stays off.
PERMISSIONS_POLICY = "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"


class PermissionsPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response
