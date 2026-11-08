import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from io import StringIO

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


class GeminiClientTests(TestCase):
    @override_settings(GEMINI_API_KEY="test-secret", GEMINI_MODEL="test-model")
    @patch("lms.ai.requests.post")
    def test_api_error_reports_google_message_without_exposing_key(self, post):
        response = post.return_value
        response.ok = False
        response.status_code = 403
        response.json.return_value = {"error": {"message": "API key is invalid."}}

        with self.assertRaises(GeminiAPIError) as raised:
            generate_json("test prompt")

        self.assertIn("HTTP 403", str(raised.exception))
        self.assertIn("API key is invalid.", str(raised.exception))
        self.assertNotIn("test-secret", str(raised.exception))


class BootstrapAdminCommandTests(TestCase):
    @patch.dict(
        os.environ,
        {
            "DJANGO_SUPERUSER_USERNAME": "renderadmin",
            "DJANGO_SUPERUSER_EMAIL": "admin@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "safe-test-password-123",
        },
    )
    def test_creates_superuser_and_does_not_reset_existing_password(self):
        output = StringIO()
        call_command("bootstrap_admin", stdout=output)
        admin = get_user_model().objects.get(username="renderadmin")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("safe-test-password-123"))
        self.assertNotIn("safe-test-password-123", output.getvalue())

        with patch.dict(os.environ, {"DJANGO_SUPERUSER_PASSWORD": "new-password-456"}):
            call_command("bootstrap_admin", stdout=StringIO())
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("safe-test-password-123"))

    @patch.dict(
        os.environ,
        {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_EMAIL": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        },
    )
    def test_skips_when_no_admin_credentials_are_configured(self):
        output = StringIO()
        call_command("bootstrap_admin", stdout=output)
        self.assertIn("skipped", output.getvalue())
        self.assertFalse(get_user_model().objects.exists())


class ModelAndFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="learner",
            password="strong-test-password",
            first_name="Ada",
            last_name="Lovelace",
        )
        self.course = Course.objects.create(title="Python", description="Python basics")
        self.lesson = VideoLesson.objects.create(
            course=self.course,
            title="Variables",
            video_url="https://example.com/variables",
            description="Names and values",
        )
        self.quiz = Quiz.objects.create(course=self.course, lesson=self.lesson, title="Basics")
        self.question = Question.objects.create(quiz=self.quiz, question_text="What is Python?")
        self.answer = Answer.objects.create(
            question=self.question,
            answer_text="A programming language",
            is_correct=True,
        )

    def test_models_have_human_readable_strings_and_delete_cascades(self):
        attempt = QuizAttempt.objects.create(
            user=self.user,
            quiz=self.quiz,
            score=100,
            correct_answers=1,
            total_questions=1,
        )
        response = QuizResponse.objects.create(
            attempt=attempt,
            question=self.question,
            selected_answer=self.answer,
            is_correct=True,
        )
        completion = CourseCompletion.objects.create(
            user=self.user,
            course=self.course,
            is_completed=True,
        )

        self.assertEqual(str(self.course), "Python")
        self.assertEqual(str(self.lesson), "Python: Variables")
        self.assertEqual(str(self.quiz), "Basics")
        self.assertEqual(str(self.question), "What is Python?")
        self.assertEqual(str(self.answer), "A programming language")
        self.assertIn("100%", str(attempt))
        self.assertIn("What is Python?", str(response))
        self.assertIn("Python", str(completion))

        self.course.delete()
        self.assertFalse(VideoLesson.objects.exists())
        self.assertFalse(Quiz.objects.exists())
        self.assertFalse(Question.objects.exists())
        self.assertFalse(Answer.objects.exists())
        self.assertFalse(QuizAttempt.objects.exists())
        self.assertFalse(QuizResponse.objects.exists())
        self.assertFalse(CourseCompletion.objects.exists())

    def test_model_forms_accept_valid_values_and_reject_missing_required_values(self):
        self.assertTrue(
            CourseForm({"title": "Django", "description": "Web development"}).is_valid()
        )
        self.assertFalse(CourseForm({"title": "", "description": ""}).is_valid())
        self.assertTrue(
            VideoLessonForm(
                {
                    "title": "Routing",
                    "video_url": "https://example.com/routing",
                    "description": "URL patterns",
                }
            ).is_valid()
        )
        self.assertFalse(
            VideoLessonForm(
                {"title": "Broken", "video_url": "not-a-url", "description": ""}
            ).is_valid()
        )


class LMSViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="learner",
            password="strong-test-password",
            first_name="Ada",
            last_name="Lovelace",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other",
            password="strong-test-password",
        )
        self.course = Course.objects.create(title="Python", description="Python basics")
        self.lesson = VideoLesson.objects.create(
            course=self.course,
            title="Variables",
            video_url="https://example.com/variables",
            description="Variables hold values.",
        )
        self.quiz = Quiz.objects.create(course=self.course, lesson=self.lesson, title="Basics")
        self.questions = []
        self.correct_answers = []
        self.wrong_answers = []
        for index in range(5):
            question = Question.objects.create(
                quiz=self.quiz,
                question_text=f"Question {index + 1}",
            )
            self.questions.append(question)
            self.correct_answers.append(
                Answer.objects.create(
                    question=question,
                    answer_text=f"Correct {index + 1}",
                    is_correct=True,
                )
            )
            self.wrong_answers.append(
                Answer.objects.create(
                    question=question,
                    answer_text=f"Wrong {index + 1}",
                    is_correct=False,
                )
            )

    def test_course_list_and_details_render(self):
        self.assertEqual(self.client.get(reverse("lms:course_list")).status_code, 200)
        response = self.client.get(reverse("lms:course_detail", args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.lesson.title)

    def test_course_and_lesson_uploads_save_correctly(self):
        response = self.client.post(
            reverse("lms:course_upload"),
            {"title": "Django", "description": "Build web apps"},
        )
        course = Course.objects.get(title="Django")
        self.assertRedirects(response, reverse("lms:course_detail", args=[course.pk]))

        response = self.client.post(
            reverse("lms:video_lesson_upload", args=[course.pk]),
            {
                "title": "Models",
                "video_url": "https://example.com/models",
                "description": "Django models",
            },
        )
        lesson = VideoLesson.objects.get(title="Models")
        self.assertEqual(lesson.course, course)
        self.assertRedirects(response, reverse("lms:lesson_detail", args=[lesson.pk]))

    @patch("lms.views.generate_json")
    def test_generate_quiz_saves_quiz_questions_and_answers(self, generate_json):
        generate_json.return_value = [
            {
                "question": "What stores a value?",
                "options": ["Variable", "Function", "Class", "Module"],
                "correctAnswer": "Variable",
            }
        ]
        self.client.force_login(self.user)

        response = self.client.post(reverse("lms:generate_quiz", args=[self.lesson.pk]))

        generated_quiz = Quiz.objects.get(lesson=self.lesson, title="Variables quiz")
        self.assertRedirects(response, reverse("lms:quiz_detail", args=[generated_quiz.pk]))
        self.assertEqual(generated_quiz.questions.count(), 1)
        self.assertEqual(generated_quiz.questions.get().answers.filter(is_correct=True).count(), 1)

    @patch("lms.views.generate_json")
    def test_generate_quiz_returns_api_format_errors_as_json(self, generate_json):
        generate_json.return_value = [{"question": "Invalid options"}]
        self.client.force_login(self.user)

        response = self.client.post(reverse("lms:generate_quiz", args=[self.lesson.pk]))

        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())
        self.assertFalse(
            Quiz.objects.filter(lesson=self.lesson, title="Variables quiz").exists()
        )

    def test_quiz_submit_grades_and_records_completion_at_passing_score(self):
        self.client.force_login(self.user)
        answers = {
            f"question_{question.pk}": (
                self.correct_answers[index].pk if index < 4 else self.wrong_answers[index].pk
            )
            for index, question in enumerate(self.questions)
        }

        response = self.client.post(reverse("lms:quiz_submit", args=[self.quiz.pk]), answers)

        attempt = QuizAttempt.objects.get(user=self.user, quiz=self.quiz)
        self.assertRedirects(response, reverse("lms:quiz_results", args=[attempt.pk]))
        self.assertEqual(attempt.score, 80)
        self.assertEqual(attempt.responses.count(), 5)
        completion = CourseCompletion.objects.get(user=self.user, course=self.course)
        self.assertTrue(completion.is_completed)
        self.assertIsNotNone(completion.completed_at)
        self.assertEqual(
            self.client.get(reverse("lms:course_detail", args=[self.course.pk])).context["completed"],
            True,
        )

    def test_quiz_submit_does_not_complete_course_for_failing_score(self):
        self.client.force_login(self.user)
        answers = {
            f"question_{question.pk}": self.correct_answers[index].pk if index < 3 else ""
            for index, question in enumerate(self.questions)
        }

        self.client.post(reverse("lms:quiz_submit", args=[self.quiz.pk]), answers)

        attempt = QuizAttempt.objects.get(user=self.user, quiz=self.quiz)
        self.assertEqual(attempt.score, 60)
        self.assertFalse(CourseCompletion.objects.filter(user=self.user, course=self.course).exists())

    def test_certificate_is_a_pdf_and_cannot_be_downloaded_for_another_user(self):
        CourseCompletion.objects.create(
            user=self.user,
            course=self.course,
            is_completed=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "lms:generate_certificate",
                args=[self.course.pk, self.user.pk],
            )
        )
        pdf = b"".join(response.streaming_content)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(
            self.client.get(
                reverse(
                    "lms:generate_certificate",
                    args=[self.course.pk, self.other_user.pk],
                )
            ).status_code,
            403,
        )

    @patch("lms.views.generate_json")
    def test_recommendations_use_search_and_link_matching_courses(self, generate_json):
        generate_json.return_value = [
            {
                "title": "Python",
                "description": "Continue with Python.",
                "relevance_score": 0.9,
            }
        ]
        self.client.force_login(self.user)

        response = self.client.get(reverse("lms:recommend_courses"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("lms:course_detail", args=[self.course.pk]))
        generate_json.assert_called_once()
        self.assertTrue(generate_json.call_args.kwargs["google_search"])
