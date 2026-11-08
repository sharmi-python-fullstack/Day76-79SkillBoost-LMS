from django.urls import path

from . import views

app_name = "lms"

urlpatterns = [
    path("", views.course_list, name="course_list"),
    path("courses/upload/", views.course_upload, name="course_upload"),
    path("courses/<int:course_id>/", views.course_detail, name="course_detail"),
    path(
        "courses/<int:course_id>/lessons/upload/",
        views.video_lesson_upload,
        name="video_lesson_upload",
    ),
    path("lessons/<int:lesson_id>/", views.lesson_detail, name="lesson_detail"),
    path("lessons/<int:lesson_id>/quizzes/generate/", views.generate_quiz, name="generate_quiz"),
    path("quizzes/<int:quiz_id>/", views.quiz_detail, name="quiz_detail"),
    path("quizzes/<int:quiz_id>/submit/", views.quiz_submit, name="quiz_submit"),
    path("quiz-attempts/<int:attempt_id>/", views.quiz_results, name="quiz_results"),
    path(
        "courses/<int:course_id>/certificates/<int:user_id>/",
        views.generate_certificate,
        name="generate_certificate",
    ),
    path("dashboard/", views.recommend_courses, name="dashboard"),
    path("recommendations/", views.recommend_courses, name="recommend_courses"),
]
