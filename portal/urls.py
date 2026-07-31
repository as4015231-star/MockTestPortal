from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/upload/<int:test_id>/', views.upload_excel, name='upload_excel'),
    path('teacher/delete-questions/<int:test_id>/', views.delete_questions, name='delete_questions'),
    path('teacher/toggle-publish/<int:test_id>/', views.toggle_publish_status, name='toggle_publish_status'),
    path('student/start-test/', views.start_test, name='start_test'),
    path('student/take-test/<int:attempt_id>/', views.take_test, name='take_test'),
    path('teacher/preview/<int:test_id>/', views.preview_test, name='preview_test'),
    path('student/instructions/<int:test_id>/', views.test_instructions, name='test_instructions'),
    path('teacher/edit-schedule/<int:test_id>/', views.edit_schedule, name='edit_schedule'),
    path('teacher/delete-test/<int:test_id>/', views.delete_test, name='delete_test'),
    path('student/result/<int:attempt_id>/', views.test_result, name='test_result'),
    path('scoreboard/<int:test_id>/', views.test_scoreboard, name='test_scoreboard'),
    path('result/<int:attempt_id>/', views.test_result, name='test_result'),
    path('celebration/<int:test_id>/', views.test_celebration, name='test_celebration'),
    path('answer-key/<int:test_id>/', views.test_answer_key, name='test_answer_key'),
    path('live-monitor/<int:test_id>/', views.live_test_monitor, name='live_test_monitor'),
    path('api/live-data/<int:test_id>/', views.api_live_data, name='api_live_data'),
    path('update-answer/<int:test_id>/', views.update_answer_key, name='update_answer_key'),
    path('choose-questions/', views.choose_questions, name='choose_questions'),
    path('api/add-bank-questions/', views.api_add_bank_questions, name='api_add_bank_questions'),
    path('delete-single-question/<int:q_id>/', views.delete_single_question, name='delete_single_question'),
    path('api/live-students/<int:test_id>/', views.api_active_students, name='api_active_students'),
    path('login/confirm-device/', views.confirm_device_login, name='confirm_device_login'),






]