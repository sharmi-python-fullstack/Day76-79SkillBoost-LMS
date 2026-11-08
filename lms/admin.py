from django.contrib import admin
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

admin.site.register(
    [Course, VideoLesson, Quiz, Question, Answer, QuizAttempt, QuizResponse, CourseCompletion]
)
