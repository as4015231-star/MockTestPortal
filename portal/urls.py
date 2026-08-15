from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Teacher Dashboard & Actions
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/upload/<int:test_id>/', views.upload_excel, name='upload_excel'),
    path('teacher/delete-questions/<int:test_id>/', views.delete_questions, name='delete_questions'),
    path('teacher/toggle-publish/<int:test_id>/', views.toggle_publish_status, name='toggle_publish_status'),
    path('teacher/preview/<int:test_id>/', views.preview_test, name='preview_test'),
    path('teacher/edit-schedule/<int:test_id>/', views.edit_schedule, name='edit_schedule'),
    path('teacher/delete-test/<int:test_id>/', views.delete_test, name='delete_test'),

    # Students Actions
    path('student/start-test/', views.start_test, name='start_test'),
    path('student/take-test/<int:attempt_id>/', views.take_test, name='take_test'),
    path('student/instructions/<int:test_id>/', views.test_instructions, name='test_instructions'),

    # 🚀 फिक्स: test_result का एक ही URL रखें
    path('student/result/<int:attempt_id>/', views.test_result, name='test_result'),

    # Test Operations & Monitoring
    path('scoreboard/<int:test_id>/', views.test_scoreboard, name='test_scoreboard'),
    path('celebration/<int:test_id>/', views.test_celebration, name='test_celebration'),
    path('answer-key/<int:test_id>/', views.test_answer_key, name='test_answer_key'),
    path('live-monitor/<int:test_id>/', views.live_test_monitor, name='live_test_monitor'),
    path('api/live-data/<int:test_id>/', views.api_live_data, name='api_live_data'),
    path('api/live-students/<int:test_id>/', views.api_active_students, name='api_active_students'),

    # 🚀 फिक्स: update-answer वाला पुराना URL हटा दिया है, अब सिर्फ नया वाला है
    path('update-answer/<int:q_id>/', views.update_correct_answer, name='update_correct_answer'),

    # Question Bank & Questions
    path('choose-questions/', views.choose_questions, name='choose_questions'),
    path('api/add-bank-questions/', views.api_add_bank_questions, name='api_add_bank_questions'),
    path('delete-single-question/<int:q_id>/', views.delete_single_question, name='delete_single_question'),
    path('upload-image/<int:q_id>/', views.upload_question_image, name='upload_question_image'),
    path('delete-image/<int:q_id>/', views.delete_question_image, name='delete_question_image'),

    # Authentication & Wallet
    path('login/confirm-device/', views.confirm_device_login, name='confirm_device_login'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('verify-reset-otp/', views.verify_reset_otp_view, name='verify_reset_otp'),
    path('reset-new-password/', views.reset_new_password_view, name='reset_new_password'),
    path('profile/', views.profile_view, name='profile'),

    # Payments
    path('payment/initiate/', views.initiate_payment, name='initiate_payment'),
    path('payment/verify/', views.verify_payment, name='verify_payment'),
    path('payment/wallet/', views.pay_via_wallet, name='pay_via_wallet'),
    path('wallet/', views.wallet_dashboard, name='wallet_dashboard'),
    path('wallet/add/', views.add_money, name='add_money'),
    path('wallet/withdraw/', views.request_withdrawal, name='request_withdrawal'),
    path('api/auto-save/', views.auto_save_answer, name='auto_save_answer'),
    path('upload-private-bank/', views.upload_private_bank, name='upload_private_bank'),
    path('api/get-subjects/', views.get_subjects, name='get_subjects'),
    path('api/get-chapters/', views.get_chapters, name='get_chapters'),
    path('api/delete-private-question/<int:q_id>/', views.api_delete_private_question, name='api_delete_private_question'),
    path('api/move-private-question/', views.api_move_private_question, name='api_move_private_question'),
    path('api/create-category/', views.api_create_category, name='api_create_category'),
    path('upload-global-bank/', views.upload_global_bank, name='upload_global_bank'),



]