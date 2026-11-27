from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CEFR_CHOICES, TRACK_CHOICES

from . import services as S
from .models import COLORS, Assignment, Classroom, Membership


class ClassSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    track = serializers.ChoiceField(choices=TRACK_CHOICES)
    level = serializers.ChoiceField(choices=CEFR_CHOICES, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    color = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", required=False)
    approval_required = serializers.BooleanField(required=False)
    org = serializers.IntegerField(required=False, allow_null=True)


class ClassPatchSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80, required=False)
    level = serializers.ChoiceField(choices=CEFR_CHOICES, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    color = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", required=False)
    approval_required = serializers.BooleanField(required=False)
    archived = serializers.BooleanField(required=False)


class AssignmentSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[k for k, _ in Assignment.KINDS])
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    level = serializers.CharField(max_length=2, required=False, allow_blank=True)
    lesson_from = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    lesson_to = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    exam_slug = serializers.CharField(max_length=60, required=False, allow_blank=True)
    topics = serializers.ListField(child=serializers.CharField(max_length=60), required=False, max_length=50)
    deck = serializers.IntegerField(required=False, allow_null=True)
    target_kind = serializers.ChoiceField(choices=[k for k, _ in Assignment.TARGETS], required=False)
    target_value = serializers.IntegerField(min_value=1, max_value=100, required=False)
    starts_on = serializers.DateField(required=False)
    due_at = serializers.DateTimeField()


def _my_classes(user) -> list[dict]:
    out = []
    for cls in S.visible_classes(user):
        teacher = S.can_teach(user, cls)
        d = S.class_dict(cls, user, teacher=teacher)
        if not teacher:
            d["open_assignments"] = cls.assignments.filter(due_at__gte=timezone.now()).count()
        out.append(d)
    return out


class ClassListView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        user = request.user
        from .models import Organization

        orgs = Organization.objects.filter(teachers=user) | Organization.objects.filter(admins=user)
        return Response(
            {
                "classes": _my_classes(user),
                "limits": S.limits("free"),
                "owned": Classroom.objects.filter(owner=user, org__isnull=True, archived=False).count(),
                "orgs": [{"id": o.id, "name": o.name} for o in orgs.distinct()],
                "colors": COLORS,
            }
        )

    @extend_schema(request=ClassSerializer, responses={201: dict})
    def post(self, request):
        ser = ClassSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cls = S.create_class(request.user, ser.validated_data)
        return Response(S.class_dict(cls, request.user, teacher=True), status=status.HTTP_201_CREATED)


class ClassDetailView(APIView):
    """Teachers get the dashboard, students their class page."""

    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        cls = S.get_class(pk)
        user = request.user
        if S.can_teach(user, cls):
            assignments = list(cls.assignments.select_related("deck"))
            rows = S.student_rows(cls, assignments)
            return Response(
                {
                    "class": S.class_dict(cls, user, teacher=True),
                    "overview": S.overview(cls, rows, assignments),
                    "students": rows,
                    "assignments": [S.assignment_dict(a) for a in assignments],
                }
            )
        m = S.membership(user, cls)
        if m is None or m.status not in (Membership.ACTIVE, Membership.PENDING):
            return Response({"detail": "class_not_found"}, status=status.HTTP_404_NOT_FOUND)
        if m.status == Membership.PENDING:
            return Response({"class": S.class_dict(cls, user, teacher=False), "assignments": [], "leaderboard": []})
        return Response(S.student_view(cls, user))

    @extend_schema(request=ClassPatchSerializer, responses={200: dict})
    def patch(self, request, pk):
        cls = S.owning(request.user, pk)
        ser = ClassPatchSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d.get("archived") is False and cls.archived:
            S.check_can_create(request.user if not cls.org_id else cls.owner, cls.org)
        for k, v in d.items():
            setattr(cls, k, v)
        cls.save()
        return Response(S.class_dict(cls, request.user, teacher=True))


class ClassActionView(APIView):
    """POST /classes/<id>/<action>/: regenerate | teacher_code | leave."""

    @extend_schema(request=None, responses={200: dict})
    def post(self, request, pk, action):
        user = request.user
        if action == "leave":
            S.leave(user, S.get_class(pk))
            return Response({"ok": True})
        cls = S.owning(user, pk)
        if action == "regenerate":
            S.regenerate_code(cls)
        elif action == "teacher_code":
            S.regenerate_teacher_code(cls)
        else:
            return Response({"detail": "unknown_action"}, status=status.HTTP_404_NOT_FOUND)
        return Response(S.class_dict(cls, user, teacher=True))


class MemberView(APIView):
    @extend_schema(request=None, responses={200: dict})
    def post(self, request, pk, user_id, action):
        cls = S.teaching(request.user, pk)
        if action == "approve":
            S.approve(cls, user_id)
        elif action == "remove":
            S.remove(cls, user_id)
        else:
            return Response({"detail": "unknown_action"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ok": True})


class StudentDetailView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request, pk, user_id):
        return Response(S.student_detail(S.teaching(request.user, pk), user_id))


class AssignmentsView(APIView):
    @extend_schema(request=AssignmentSerializer, responses={201: dict})
    def post(self, request, pk):
        cls = S.teaching(request.user, pk)
        ser = AssignmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        a = S.create_assignment(cls, request.user, ser.validated_data)
        return Response(S.assignment_dict(a), status=status.HTTP_201_CREATED)


class AssignmentDetailView(APIView):
    @extend_schema(responses={204: None})
    def delete(self, request, pk, aid):
        cls = S.teaching(request.user, pk)
        cls.assignments.filter(pk=aid).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HardestView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        return Response({"words": S.hardest_words(S.teaching(request.user, pk))})

    @extend_schema(request=dict, responses={201: dict})
    def post(self, request, pk):
        """Create a deck from these words and assign it."""
        cls = S.teaching(request.user, pk)
        raw_due = request.data.get("due_at")
        due = serializers.DateTimeField().to_internal_value(raw_due) if raw_due else timezone.now() + timedelta(days=7)
        terms = request.data.get("terms") or None
        a = S.deck_from_hardest(cls, request.user, terms, due, int(request.data.get("target_value") or 80))
        return Response(S.assignment_dict(a), status=status.HTTP_201_CREATED)


class LeaderboardView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        cls = S.get_class(pk)
        if not (S.can_teach(request.user, cls) or S.is_student(request.user, cls)):
            return Response({"detail": "class_not_found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"entries": S.leaderboard(cls, request.user.id)})


class AnnounceView(APIView):
    @extend_schema(request=dict, responses={201: dict})
    def post(self, request, pk):
        cls = S.teaching(request.user, pk)
        text = str(request.data.get("text") or "")[:2000]
        ann = S.announce(cls, request.user, text)
        from broadcasts.services import audience

        recipients = audience("class", str(cls.id)).count()
        return Response({"id": ann.id, "recipients": recipients}, status=status.HTTP_201_CREATED)


class ExportView(APIView):
    @extend_schema(responses={200: str})
    def get(self, request, pk):
        cls = S.teaching(request.user, pk)
        resp = HttpResponse(S.export_csv(cls), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="class-{cls.id}.csv"'
        return resp


class JoinView(APIView):
    """GET: preview of the class behind a code. POST: join (or ask to join)."""

    @extend_schema(responses={200: dict})
    def get(self, request, code):
        cls = S.by_code(code)
        m = S.membership(request.user, cls)
        return Response(
            {
                "id": cls.id,
                "name": cls.name,
                "track": cls.track,
                "level": cls.level,
                "description": cls.description,
                "color": cls.color,
                "teacher": S.person(cls.owner),
                "students": S.active_count(cls),
                "approval_required": cls.approval_required,
                "membership": m.status if m else None,
                "is_teacher": S.can_teach(request.user, cls),
            }
        )

    @extend_schema(request=None, responses={200: dict})
    def post(self, request, code):
        m = S.join(request.user, code)
        return Response({"id": m.classroom_id, "membership": m.status})


class TeachJoinView(APIView):
    @extend_schema(request=None, responses={200: dict})
    def post(self, request, code):
        cls = S.join_as_teacher(request.user, code)
        return Response({"id": cls.id})
