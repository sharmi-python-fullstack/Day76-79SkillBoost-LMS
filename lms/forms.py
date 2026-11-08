from django import forms

from .models import Course, VideoLesson


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["title", "description"]


class VideoLessonForm(forms.ModelForm):
    class Meta:
        model = VideoLesson
        fields = ["title", "video_url", "description"]
