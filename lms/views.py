import io
import logging
from html import escape

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .ai import GeminiAPIError, generate_json
from .forms import CourseForm, VideoLessonForm
from .models import (
    Answer,
    Course,
    CourseCompletion,
    Question,
    Quiz,
    QuizAttempt,
    QuizResponse,
    VideoLesson,
)

logger = logging.getLogger(__name__)


def course_list(request):
    courses = Course.objects.order_by("-created_at")
    return render(request, "lms/course_list.html", {"courses": courses})


def course_upload(request):
    form = CourseForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        course = form.save()
        messages.success(request, "Course created successfully.")
        return redirect("lms:course_detail", course_id=course.pk)
    return render(request, "lms/course_upload.html", {"form": form})


def course_detail(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    completed = False
    if request.user.is_authenticated:
        completed = CourseCompletion.objects.filter(
            user=request.user,
            course=course,
            is_completed=True,
        ).exists()
    return render(
        request,
        "lms/course_detail.html",
        {"course": course, "completed": completed},
    )


def video_lesson_upload(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    form = VideoLessonForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        lesson = form.save(commit=False)
        lesson.course = course
        lesson.save()
        messages.success(request, "Video lesson created successfully.")
        return redirect("lms:lesson_detail", lesson_id=lesson.pk)
    return render(
        request,
        "lms/video_lesson_upload.html",
        {"form": form, "course": course},
    )


def lesson_detail(request, lesson_id):
    lesson = get_object_or_404(VideoLesson.objects.select_related("course"), pk=lesson_id)
    return render(request, "lms/video_lesson_detail.html", {"lesson": lesson})


@login_required
@require_POST
def generate_quiz(request, lesson_id):
    lesson = get_object_or_404(VideoLesson.objects.select_related("course"), pk=lesson_id)
    prompt = (
        "Act as a careful educational quiz generator. Use the lesson description below "
        "as source material. Return only a JSON array of 5 multiple-choice question "
        "objects, each with a string `question`, an `options` array of 4 distinct "
        "strings, and a `correctAnswer` string that exactly matches one option. "
        "Do not include markdown or commentary.\n\n"
        f"Lesson title: {lesson.title}\nDescription: {lesson.description}"
    )
    try:
        generated = generate_json(prompt)
        validated = []
        for item in generated:
            if not isinstance(item, dict):
                raise GeminiAPIError("A generated question had an invalid format.")
            question_text = item.get("question")
            options = item.get("options")
            correct_answer = item.get("correctAnswer")
            if (
                not isinstance(question_text, str)
                or not question_text.strip()
                or not isinstance(options, list)
                or len(options) != 4
                or not all(isinstance(option, str) and option.strip() for option in options)
                or len(set(options)) != len(options)
                or any(len(option) > 500 for option in options)
                or not isinstance(correct_answer, str)
                or correct_answer not in options
            ):
                raise GeminiAPIError("A generated question did not match the required format.")
            validated.append((question_text.strip(), options, correct_answer))
        if not validated:
            raise GeminiAPIError("The Gemini API did not generate any questions.")
    except GeminiAPIError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    try:
        with transaction.atomic():
            quiz = Quiz.objects.create(
                course=lesson.course,
                lesson=lesson,
                title=f"{lesson.title} quiz",
            )
            for question_text, options, correct_answer in validated:
                question = Question.objects.create(quiz=quiz, question_text=question_text)
                Answer.objects.bulk_create(
                    [
                        Answer(
                            question=question,
                            answer_text=option,
                            is_correct=option == correct_answer,
                        )
                        for option in options
                    ]
                )
    except Exception:
        logger.exception("Could not save generated quiz for lesson %s", lesson.pk)
        return JsonResponse({"error": "The generated quiz could not be saved."}, status=500)

    messages.success(request, "Quiz generated successfully.")
    return redirect("lms:quiz_detail", quiz_id=quiz.pk)


def quiz_detail(request, quiz_id):
    quiz = get_object_or_404(
        Quiz.objects.prefetch_related("questions__answers"),
        pk=quiz_id,
    )
    return render(request, "lms/quiz_detail.html", {"quiz": quiz})


@login_required
@require_POST
def quiz_submit(request, quiz_id):
    quiz = get_object_or_404(Quiz.objects.select_related("course"), pk=quiz_id)
    questions = list(quiz.questions.prefetch_related("answers").all())
    if not questions:
        messages.error(request, "This quiz has no questions to grade.")
        return redirect("lms:quiz_detail", quiz_id=quiz.pk)

    correct_count = 0
    responses = []
    for question in questions:
        answer_id = request.POST.get(f"question_{question.pk}")
        selected_answer = None
        if answer_id:
            selected_answer = next(
                (answer for answer in question.answers.all() if str(answer.pk) == answer_id),
                None,
            )
        is_correct = bool(selected_answer and selected_answer.is_correct)
        correct_count += is_correct
        responses.append((question, selected_answer, is_correct))
    total_questions = len(questions)
    score = round(correct_count * 100 / total_questions)

    with transaction.atomic():
        attempt = QuizAttempt.objects.create(
            user=request.user,
            quiz=quiz,
            score=score,
            correct_answers=correct_count,
            total_questions=total_questions,
        )
        QuizResponse.objects.bulk_create(
            [
                QuizResponse(
                    attempt=attempt,
                    question=question,
                    selected_answer=selected_answer,
                    is_correct=is_correct,
                )
                for question, selected_answer, is_correct in responses
            ]
        )
        if score >= 80:
            completion, created = CourseCompletion.objects.get_or_create(
                user=request.user,
                course=quiz.course,
                defaults={"is_completed": True, "completed_at": timezone.now()},
            )
            if not created and not completion.is_completed:
                completion.is_completed = True
                completion.completed_at = timezone.now()
                completion.save(update_fields=["is_completed", "completed_at"])

    return redirect("lms:quiz_results", attempt_id=attempt.pk)


@login_required
def quiz_results(request, attempt_id):
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz__course").prefetch_related(
            "responses__question__answers",
            "responses__selected_answer",
        ),
        pk=attempt_id,
        user=request.user,
    )
    return render(request, "lms/quiz_results.html", {"attempt": attempt})


@login_required
def generate_certificate(request, course_id, user_id):
    if request.user.pk != user_id:
        return JsonResponse({"error": "You can only download your own certificate."}, status=403)
    course = get_object_or_404(Course, pk=course_id)
    completion = get_object_or_404(
        CourseCompletion,
        user=request.user,
        course=course,
        is_completed=True,
    )
    completed_at = completion.completed_at or timezone.now()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    styles = getSampleStyleSheet()
    story = [
        Spacer(1, 90),
        Paragraph("Certificate of Completion", styles["Title"]),
        Spacer(1, 30),
        Paragraph(
            f"This certifies that <b>{escape(request.user.get_full_name() or request.user.username)}</b>",
            styles["Heading2"],
        ),
        Spacer(1, 18),
        Paragraph(f"has successfully completed <b>{escape(course.title)}</b>.", styles["Heading2"]),
        Spacer(1, 24),
        Paragraph(f"Completed on {completed_at:%B %d, %Y}", styles["Normal"]),
    ]

    def draw_border(canvas, _document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#3157a4"))
        canvas.setLineWidth(3)
        canvas.rect(28, 28, landscape(letter)[0] - 56, landscape(letter)[1] - 56)
        canvas.restoreState()

    document.build(story, onFirstPage=draw_border)
    buffer.seek(0)
    filename = f"skillboost-certificate-course-{course.pk}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")


@login_required
def recommend_courses(request):
    completions = list(
        CourseCompletion.objects.filter(user=request.user, is_completed=True)
        .select_related("course")
        .order_by("-completed_at")[:5]
    )
    attempts = list(
        QuizAttempt.objects.filter(user=request.user)
        .select_related("quiz__course")
        .order_by("-created_at")[:5]
    )
    history = [
        {
            "course": completion.course.title,
            "completed": completion.completed_at.isoformat() if completion.completed_at else None,
        }
        for completion in completions
    ]
    quiz_history = [
        {"course": attempt.quiz.course.title, "score": attempt.score}
        for attempt in attempts
    ]
    prompt = (
        "Recommend up to 5 learning courses personalized to this learner. Use recent "
        "course completion and quiz results, and provide brief useful descriptions. "
        "Return only a JSON array with objects containing string `title`, string "
        "`description`, and numeric `relevance_score` from 0 to 1. Do not include "
        "markdown or commentary.\n"
        f"Completed courses: {history}\nQuiz results: {quiz_history}"
    )
    recommendations = []
    has_unmatched_recommendations = False
    error = None
    try:
        generated = generate_json(prompt, google_search=True)
        for item in generated:
            if not isinstance(item, dict):
                raise GeminiAPIError("A recommendation had an invalid format.")
            title = item.get("title")
            description = item.get("description")
            relevance = item.get("relevance_score")
            if (
                not isinstance(title, str)
                or not title.strip()
                or not isinstance(description, str)
                or isinstance(relevance, bool)
                or not isinstance(relevance, (int, float))
                or not 0 <= relevance <= 1
            ):
                raise GeminiAPIError("A recommendation did not match the required format.")
            matching_course = Course.objects.filter(title__iexact=title.strip()).first()
            if matching_course is None:
                has_unmatched_recommendations = True
                continue
            recommendation = {
                "title": title.strip(),
                "description": description.strip(),
                "relevance_score": relevance,
                "course": matching_course,
            }
            recommendations.append(recommendation)
    except GeminiAPIError as exc:
        error = str(exc)
        logger.warning("Course recommendations unavailable for user %s: %s", request.user.pk, exc)

    return render(
        request,
        "lms/recommendations.html",
        {
            "recommendations": recommendations,
            "error": error,
            "has_unmatched_recommendations": has_unmatched_recommendations,
        },
    )
