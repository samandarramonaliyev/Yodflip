from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


class LeagueView(APIView):
    """The current week: tier, my group's ranking with zones, countdown, last result."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(services.state(request.user))


class LeagueHistoryView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({"weeks": services.history(request.user)})
