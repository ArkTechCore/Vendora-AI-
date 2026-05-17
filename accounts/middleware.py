class NoCacheForAuthMiddleware:
    """
    Prevent stale authenticated pages from appearing through browser Back.
    This does not replace permissions; it just keeps auth screens and protected
    pages from being reused from browser cache after logout.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        is_auth_page = request.path.startswith("/accounts/")
        is_authenticated = bool(user and user.is_authenticated)
        if is_auth_page or is_authenticated:
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            response.setdefault("Vary", "Cookie")
        return response
