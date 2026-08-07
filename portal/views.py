import random
import re
import json
import openpyxl
import razorpay
from decimal import Decimal  # 🚀 NEW: Decimal को ग्लोबली इम्पोर्ट किया गया है
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.mail import send_mail
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.contrib.sessions.models import Session

from .models import CustomUser, TeacherProfile, StudentProfile, MockTest, Question, TestAttempt, StudentAnswer, \
    QuestionCategory, QuestionSubCategory, QuestionChapter, GlobalQuestionBank, PaymentTransaction, WalletTransaction, WithdrawalRequest

# Razorpay Client Setup
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q




# 1. होम पेज
def home(request):
    context = {}
    if request.user.is_authenticated and request.user.role == 'STUDENT':
        # यहाँ हम चेक कर रहे हैं कि बच्चे का प्लान एक्टिव है या नहीं
        student = request.user.student_profile
        context['has_plan'] = student.has_active_plan()

    return render(request, 'portal/home.html', context)

# 2. रजिस्ट्रेशन और OTP भेजना
def signup_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        mobile_number = request.POST.get('mobile_number')
        email = request.POST.get('email')
        coaching_code = request.POST.get('coaching_code')
        password = request.POST.get('password')

        if CustomUser.objects.filter(mobile_number=mobile_number).exists():
            messages.error(request, 'यह मोबाइल नंबर पहले से रजिस्टर है।')
            return redirect('signup')

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, 'यह ईमेल पहले से रजिस्टर है।')
            return redirect('signup')

        try:
            teacher = TeacherProfile.objects.get(coaching_code=coaching_code)
        except TeacherProfile.DoesNotExist:
            messages.error(request, 'कोचिंग कोड गलत है! कृपया सही कोड डालें।')
            return redirect('signup')

        otp = str(random.randint(100000, 999999))

        request.session['temp_user'] = {
            'full_name': full_name, 'mobile_number': mobile_number,
            'email': email, 'coaching_code': coaching_code, 'password': password
        }
        request.session['otp'] = otp

        send_mail(
            'आपका KBC पोर्टल OTP',
            f'आपका रजिस्ट्रेशन OTP है: {otp}',
            'admin@kbcportal.com',
            [email],
            fail_silently=False,
        )

        return redirect('verify_otp')

    return render(request, 'portal/signup.html')


# 3. OTP वेरिफिकेशन और अकाउंट बनाना
def verify_otp_view(request):
    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        saved_otp = request.session.get('otp')
        user_data = request.session.get('temp_user')

        if entered_otp == saved_otp and user_data:
            user = CustomUser.objects.create_user(
                mobile_number=user_data['mobile_number'],
                email=user_data['email'],
                password=user_data['password'],
                full_name=user_data['full_name'],
                role='STUDENT'
            )
            teacher = TeacherProfile.objects.get(coaching_code=user_data['coaching_code'])
            StudentProfile.objects.create(user=user, enrolled_coaching=teacher)

            del request.session['temp_user']
            del request.session['otp']

            messages.success(request, 'अकाउंट सफलतापूर्वक बन गया! अब आप लॉगिन कर सकते हैं।')
            return redirect('login')
        else:
            messages.error(request, 'OTP गलत है! कृपया दोबारा प्रयास करें।')

    return render(request, 'portal/verify_otp.html')


# 4. स्मार्ट लॉगिन सिस्टम
def login_view(request):
    if request.method == 'POST':
        mobile_number = request.POST.get('mobile_number')
        password = request.POST.get('password')

        user = authenticate(request, mobile_number=mobile_number, password=password)

        if user is not None:
            if user.last_session_key:
                session_exists = Session.objects.filter(session_key=user.last_session_key).exists()
                if session_exists:
                    request.session['pre_auth_user_id'] = user.id
                    return redirect('confirm_device_login')

            login(request, user)
            user.last_session_key = request.session.session_key
            user.save()

            if user.role == 'TEACHER':
                return redirect('teacher_dashboard')
            return redirect('home')
        else:
            messages.error(request, 'मोबाइल नंबर या पासवर्ड गलत है!')

    return render(request, 'portal/login.html')


def confirm_device_login(dict_request_or_real):
    request = dict_request_or_real
    user_id = request.session.get('pre_auth_user_id')
    if not user_id:
        return redirect('login')

    user = CustomUser.objects.get(id=user_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'remain':
            if 'pre_auth_user_id' in request.session:
                del request.session['pre_auth_user_id']
            messages.info(request, "लॉगिन रद्द किया गया। आप अपने पिछले डिवाइस पर लॉगिन बने हुए हैं।")
            return redirect('login')

        elif action == 'kickout':
            try:
                old_session = Session.objects.get(session_key=user.last_session_key)
                old_session.delete()
            except Session.DoesNotExist:
                pass

            login(request, user)
            user.last_session_key = request.session.session_key
            user.save()

            if 'pre_auth_user_id' in request.session:
                del request.session['pre_auth_user_id']

            if user.role == 'TEACHER':
                return redirect('teacher_dashboard')
            return redirect('home')

    return render(request, 'portal/confirm_device.html', {'target_user': user})


# 5. लॉगआउट सिस्टम
def logout_view(request):
    logout(request)
    return redirect('login')


# --- टीचर डैशबोर्ड और टेस्ट मैनेजमेंट ---
@login_required
def teacher_dashboard(request):
    if request.user.role != 'TEACHER':
        return redirect('home')

    teacher_profile = request.user.teacher_profile
    form_data = {}

    # 🚀 1. क्रिएट टेस्ट का लॉजिक (आपका पुराना कोड)
    if request.method == 'POST' and 'create_test' in request.POST:
        form_data = request.POST
        title = request.POST.get('title')
        test_code = request.POST.get('test_code').upper().strip()
        total_time = request.POST.get('total_time')
        correct_marks = request.POST.get('correct_marks')
        negative_marks = request.POST.get('negative_marks')
        scheduled_time = request.POST.get('scheduled_time')

        if not scheduled_time:
            scheduled_time = None

        if MockTest.objects.filter(test_code=test_code).exists():
            messages.error(request, f'टेस्ट कोड "{test_code}" पहले से मौजूद है! कृपया नया कोड डालें।')
        else:
            MockTest.objects.create(
                teacher=teacher_profile, title=title, test_code=test_code,
                total_time=total_time, correct_marks=correct_marks,
                negative_marks=negative_marks, scheduled_time=scheduled_time, status='DRAFT'
            )
            messages.success(request, f'टेस्ट "{title}" बन गया है! अब Excel अपलोड करें।')
            return redirect('teacher_dashboard')

    # ---------------------------------------------------------
    # 🚀 2. NEW: AUTO-DRAFT LOGIC (समय खत्म होने पर टेस्ट ड्राफ्ट करना)
    # ---------------------------------------------------------
    published_tests = MockTest.objects.filter(teacher=teacher_profile, status='PUBLISHED')
    current_time = timezone.now()

    for test in published_tests:
        # चेक करें कि टेस्ट में शेड्यूल्ड टाइम और टोटल टाइम सेट है या नहीं
        if test.scheduled_time and test.total_time:
            # टेस्ट खत्म होने का समय = शुरू होने का समय + टेस्ट की अवधि (मिनटों में)
            end_time = test.scheduled_time + timedelta(minutes=int(test.total_time))

            # अगर अभी का समय, टेस्ट खत्म होने के समय से आगे निकल गया है
            if current_time > end_time:
                test.status = 'DRAFT'
                test.save()
    # ---------------------------------------------------------

    # 🚀 3. डैशबोर्ड पर दिखाने के लिए सारे टेस्ट मंगाएं (लेटेस्ट सबसे ऊपर)
    tests = MockTest.objects.filter(teacher=teacher_profile).order_by('-created_at')

    return render(request, 'portal/teacher_dashboard.html', {'tests': tests, 'form_data': form_data})



@login_required
def toggle_publish_status(request, test_id):
    if request.user.role != 'TEACHER':
        return redirect('home')
    try:
        test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
        if test.status == 'DRAFT':
            if test.questions.count() == 0:
                messages.error(request, 'एरर: बिना प्रश्न अपलोड किए आप टेस्ट को पब्लिश नहीं कर सकते!')
                return redirect('teacher_dashboard')
            test.status = 'PUBLISHED'
            messages.success(request, f'टेस्ट "{test.title}" अब लाइव (Published) हो गया है!')
        else:
            test.status = 'DRAFT'
            messages.success(request, f'टेस्ट "{test.title}" अब ड्राफ्ट मोड में आ गया है।')
        test.save()
    except MockTest.DoesNotExist:
        messages.error(request, 'टेस्ट नहीं मिला।')
    return redirect('teacher_dashboard')


@login_required
def edit_schedule(request, test_id):
    if request.user.role != 'TEACHER':
        return redirect('home')
    try:
        test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
        if request.method == 'POST':
            new_title = request.POST.get('new_title')
            new_code = request.POST.get('new_test_code').upper().strip()
            new_time_duration = request.POST.get('new_total_time')
            new_correct = request.POST.get('new_correct_marks')
            new_negative = request.POST.get('new_negative_marks')
            new_scheduled_time = request.POST.get('new_scheduled_time')

            if new_code != test.test_code:
                if MockTest.objects.filter(test_code=new_code).exists():
                    messages.error(request, f'टेस्ट कोड "{new_code}" पहले से इस्तेमाल में है!')
                    return redirect('teacher_dashboard')

                with transaction.atomic():
                    new_test = MockTest.objects.create(
                        teacher=test.teacher, title=new_title, test_code=new_code,
                        total_time=new_time_duration, correct_marks=new_correct,
                        negative_marks=new_negative, scheduled_time=new_scheduled_time if new_scheduled_time else None,
                        status='DRAFT'
                    )
                    for q in test.questions.all():
                        q.pk = None
                        q.test = new_test
                        q.save()
                messages.success(request, f'नया टेस्ट "{new_test.title}" सफलता से कॉपी और अपडेट हो गया!')

            else:
                test.title = new_title
                test.total_time = new_time_duration
                test.correct_marks = new_correct
                test.negative_marks = new_negative
                test.scheduled_time = new_scheduled_time if new_scheduled_time else None
                test.save()
                messages.success(request, 'टेस्ट सेटिंग्स सफलतापूर्वक अपडेट हो गईं!')

    except Exception as e:
        messages.error(request, 'कुछ गलती हुई।')
    return redirect('teacher_dashboard')


@login_required
def delete_test(request, test_id):
    if request.user.role != 'TEACHER':
        return redirect('home')

    try:
        test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
        test_title = test.title
        test.delete()
        messages.success(request, f'टेस्ट "{test_title}" हमेशा के लिए सफलतापूर्वक डिलीट कर दिया गया है!')
    except MockTest.DoesNotExist:
        messages.error(request, 'टेस्ट नहीं मिला या आपको इसे डिलीट करने का अधिकार नहीं है।')

    return redirect('teacher_dashboard')


@login_required
def preview_test(request, test_id):
    test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
    questions = test.questions.all()
    return render(request, 'portal/preview_test.html', {'test': test, 'questions': questions})


@login_required
def upload_excel(request, test_id):
    test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)

    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            wb = openpyxl.load_workbook(excel_file)
            sheet = wb.active
            count = 0
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]:
                    continue
                Question.objects.create(
                    test=test,
                    question_text=str(row[0]),
                    option_a=str(row[1]),
                    option_b=str(row[2]),
                    option_c=str(row[3]),
                    option_d=str(row[4]),
                    correct_answer=str(row[5]).strip().upper(),
                    explanation=str(row[6]) if len(row) > 6 and row[6] else ""
                )
                count += 1
            messages.success(request, f'✅ सफलता! आपके {count} प्रश्न सफलतापूर्वक अपलोड हो गए हैं।')
        except Exception as e:
            messages.error(request, f'एक्सेल फाइल पढ़ने में एरर: {str(e)}')
        return redirect('teacher_dashboard')

    return render(request, 'portal/upload_excel.html', {'test': test})


@login_required
def delete_questions(request, test_id):
    test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
    test.questions.all().delete()
    messages.success(request, '🗑️ सारे प्रश्न सफलतापूर्वक हटा दिए गए हैं। अब आप नई फाइल अपलोड कर सकते हैं।')
    return redirect('teacher_dashboard')


# --- छात्र एग्जाम इंजन ---
@login_required
def start_test(request):
    if request.user.role != 'STUDENT':
        messages.error(request, 'केवल छात्र ही टेस्ट दे सकते हैं।')
        return redirect('teacher_dashboard')

    # 🚀 BACKEND LOCK: अगर कोई चालाकी से टेस्ट स्टार्ट करना चाहे, तो उसे रोककर पेमेंट पेज पर भेजें
    student = request.user.student_profile
    if not student.has_active_plan():
        messages.warning(request, 'आपका फ्री ट्रायल समाप्त हो चुका है। कृपया आगे टेस्ट देने के लिए पेमेंट करें।')
        return redirect('initiate_payment')

    if request.method == 'POST':
        test_code = request.POST.get('test_code').strip().upper()
        try:
            test = MockTest.objects.get(test_code=test_code, status='PUBLISHED')
        except MockTest.DoesNotExist:
            messages.error(request, 'गलत टेस्ट कोड! या टेस्ट अभी लाइव नहीं हुआ है।')
            return redirect('home')

        attempt = TestAttempt.objects.filter(student=request.user.student_profile, test=test, is_completed=True).first()

        if attempt:
            messages.error(request, 'आप यह टेस्ट पहले ही दे चुके हैं!')
            return redirect('home')

        return redirect('test_instructions', test_id=test.id)

    return redirect('home')

@login_required
def take_test(request, attempt_id):
    attempt = TestAttempt.objects.get(id=attempt_id, student=request.user.student_profile)

    if attempt.is_completed:
        messages.info(request, 'यह टेस्ट सबमिट हो चुका है।')
        return redirect('test_result', attempt_id=attempt.id)

    test = attempt.test
    questions = test.questions.all()

    coaching_name = test.teacher.user.full_name
    mobile_last_4 = str(request.user.mobile_number)[-4:]
    student_display_name = f"{request.user.full_name} ({mobile_last_4})"

    if request.method == 'POST':
        total_score = Decimal('0.00')
        for q in questions:
            selected = request.POST.get(f'question_{q.id}')
            StudentAnswer.objects.create(
                attempt=attempt,
                question=q,
                selected_option=selected
            )
            if selected:
                if selected == q.correct_answer:
                    total_score += test.correct_marks
                else:
                    total_score -= test.negative_marks

        attempt.score = total_score
        attempt.is_completed = True
        attempt.save()

        messages.success(request, f'🎉 टेस्ट सफलतापूर्वक सबमिट हो गया!')
        return redirect('test_result', attempt_id=attempt.id)

    remaining_seconds = test.total_time * 60
    is_strict = False

    if test.scheduled_time:
        is_strict = True
        now = timezone.now()
        end_time = test.scheduled_time + timedelta(minutes=test.total_time)

        if now >= end_time:
            attempt.is_completed = True
            attempt.save()
            messages.error(request, 'टेस्ट का निर्धारित समय समाप्त हो चुका है!')
            return redirect('test_result', attempt_id=attempt.id)
        else:
            remaining_seconds = int((end_time - now).total_seconds())

    return render(request, 'portal/take_test.html', {
        'attempt': attempt,
        'test': test,
        'questions': questions,
        'coaching_name': coaching_name,
        'student_display_name': student_display_name,
        'is_strict': is_strict,
        'remaining_seconds': remaining_seconds
    })


# --- 1. Result View ---
@login_required
def test_result(request, attempt_id):
    if request.user.role != 'STUDENT':
        return redirect('home')

    try:
        attempt = TestAttempt.objects.get(id=attempt_id, student=request.user.student_profile)
        test = attempt.test
        student_answers = attempt.answers.all()

        coaching_name = test.teacher.user.full_name
        mobile_last_4 = str(request.user.mobile_number)[-4:]
        student_display_name = f"{request.user.full_name} ({mobile_last_4})"

        total_questions = test.questions.count()
        attempted = student_answers.exclude(selected_option__isnull=True).exclude(selected_option='').count()
        unattempted = total_questions - attempted

        correct_answers = 0
        wrong_answers = 0
        answer_data = []

        for q in test.questions.all():
            ans = student_answers.filter(question=q).first()
            selected = ans.selected_option if ans else None
            is_correct = False

            if selected:
                if selected == q.correct_answer:
                    correct_answers += 1
                    is_correct = True
                else:
                    wrong_answers += 1

            answer_data.append({'question': q, 'selected': selected, 'is_correct': is_correct})

        total_score = (Decimal(correct_answers) * test.correct_marks) - (Decimal(wrong_answers) * test.negative_marks)

        if attempt.score != total_score:
            attempt.score = total_score
            attempt.save(update_fields=['score'])

        context = {
            'test': test, 'attempt': attempt, 'total_questions': total_questions,
            'attempted': attempted, 'unattempted': unattempted, 'correct_answers': correct_answers,
            'wrong_answers': wrong_answers, 'total_score': total_score, 'answer_data': answer_data,
            'coaching_name': coaching_name, 'student_display_name': student_display_name
        }
        return render(request, 'portal/test_result.html', context)
    except TestAttempt.DoesNotExist:
        messages.error(request, 'रिजल्ट नहीं मिला!')
        return redirect('home')


# --- 2. Scoreboard (UPDATED WITH DENSE RANKING) ---
@login_required
def test_scoreboard(request, test_id):
    test = MockTest.objects.get(id=test_id)
    attempts = TestAttempt.objects.filter(test=test, is_completed=True)
    questions = test.questions.all().order_by('id')
    coaching_name = test.teacher.user.full_name

    student_data = []
    for attempt in attempts:
        student_answers = attempt.answers.all()
        ans_dict = {ans.question_id: ans.selected_option for ans in student_answers}
        score = Decimal('0.00')
        q_answers = {}
        for q in questions:
            selected = ans_dict.get(q.id)
            is_correct = None
            opt_text = ""
            if selected:
                opt_text = getattr(q, f"option_{selected.lower()}")
                opt_text = f"{selected}. {opt_text}"
                if selected == q.correct_answer:
                    score += test.correct_marks
                    is_correct = True
                else:
                    score -= test.negative_marks
                    is_correct = False
            q_answers[q.id] = {'text': opt_text, 'is_correct': is_correct, 'selected_letter': selected}

        mobile_4 = str(attempt.student.user.mobile_number)[-4:]
        unique_name = f"{attempt.student.user.full_name} ({mobile_4})"
        student_data.append({'name': unique_name, 'score': score, 'answers': q_answers})

    student_data.sort(key=lambda x: x['score'], reverse=True)

    current_rank = 1
    previous_score = None

    for student in student_data:
        if previous_score is None:
            student['rank'] = current_rank
        elif student['score'] < previous_score:
            current_rank += 1
            student['rank'] = current_rank
        else:
            student['rank'] = current_rank

        previous_score = student['score']

    for student in student_data:
        student['name'] = f"Rank {student['rank']} | {student['name']}"

    rows = []
    for index, q in enumerate(questions, 1):
        row_cells = []
        for student in student_data:
            cell = student['answers'][q.id].copy()
            cell['student_name'] = student['name']
            row_cells.append(cell)

        clean_q_text = re.sub(r'^Row\s*\d+:\s*', '', q.question_text, flags=re.IGNORECASE)

        rows.append({
            'q_number': index,
            'q_text': clean_q_text,
            'opt_a': q.option_a,
            'opt_b': q.option_b,
            'opt_c': q.option_c,
            'opt_d': q.option_d,
            'correct_ans': q.correct_answer,
            'cells': row_cells
        })

    return render(request, 'portal/scoreboard.html', {
        'test': test,
        'student_data': student_data,
        'rows': rows,
        'coaching_name': coaching_name
    })


# --- 3. Celebration View (UPDATED WITH JOINT WINNERS LOGIC) ---
@login_required
def test_celebration(request, test_id):
    test = MockTest.objects.get(id=test_id)

    attempts = TestAttempt.objects.filter(test=test, is_completed=True).order_by('-score')

    winners = []
    highest_score = Decimal('0.00')

    if attempts.exists():
        for attempt in attempts:
            if attempt.score is None:
                correct = sum(1 for ans in attempt.answers.all() if ans.selected_option == ans.question.correct_answer)
                wrong = sum(1 for ans in attempt.answers.all() if
                            ans.selected_option and ans.selected_option != ans.question.correct_answer)
                attempt.score = (Decimal(correct) * test.correct_marks) - (Decimal(wrong) * test.negative_marks)
                attempt.save(update_fields=['score'])

        attempts = TestAttempt.objects.filter(test=test, is_completed=True).order_by('-score')
        highest_score = attempts.first().score

        winners = attempts.filter(score=highest_score)

    return render(request, 'portal/celebration.html', {
        'test': test,
        'winners': winners,
        'highest_score': highest_score
    })


# --- 4. Answer Key & Certificate View (UPDATED WITH JOINT RANK CALCULATION) ---
@login_required
def test_answer_key(request, test_id):
    test = MockTest.objects.get(id=test_id)
    questions = test.questions.all()

    attempts = TestAttempt.objects.filter(test=test, is_completed=True).order_by('-score')

    current_rank = 1
    previous_score = None
    student_attempt = None

    for attempt in attempts:
        if attempt.score is None:
            correct = sum(1 for ans in attempt.answers.all() if ans.selected_option == ans.question.correct_answer)
            wrong = sum(1 for ans in attempt.answers.all() if
                        ans.selected_option and ans.selected_option != ans.question.correct_answer)
            attempt.score = (Decimal(correct) * test.correct_marks) - (Decimal(wrong) * test.negative_marks)
            attempt.save(update_fields=['score'])

        if previous_score is None:
            attempt.rank = current_rank
        elif attempt.score < previous_score:
            current_rank += 1
            attempt.rank = current_rank
        else:
            attempt.rank = current_rank

        previous_score = attempt.score

        if request.user.role == 'STUDENT' and attempt.student == request.user.student_profile:
            student_attempt = attempt

    coaching_name = test.teacher.user.full_name

    return render(request, 'portal/answer_key.html', {
        'test': test,
        'questions': questions,
        'student_attempt': student_attempt,
        'coaching_name': coaching_name
    })


# 1. टीचर का लाइव कंट्रोल रूम
@login_required
def live_test_monitor(request, test_id):
    if request.user.role != 'TEACHER':
        return redirect('home')
    test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
    questions = test.questions.all().order_by('id')
    return render(request, 'portal/live_monitor.html', {'test': test, 'questions': questions})


# 2. लाइव डेटा API
@login_required
def api_live_data(request, test_id):
    if request.user.role != 'TEACHER':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    test = MockTest.objects.get(id=test_id)
    teacher = test.teacher

    all_students = StudentProfile.objects.filter(enrolled_coaching=teacher)
    attempts = TestAttempt.objects.filter(test=test)
    attempted_student_ids = attempts.values_list('student_id', flat=True)

    students_data = []

    for attempt in attempts:
        mobile_4 = str(attempt.student.user.mobile_number)[-4:]
        status = "Submitted" if attempt.is_completed else "Solving..."
        students_data.append({
            'name': f"{attempt.student.user.full_name} ({mobile_4})",
            'status': status,
            'score': attempt.score if attempt.is_completed else "-",
            'color': 'green'
        })

    pending_students = all_students.exclude(id__in=attempted_student_ids)
    for st in pending_students:
        mobile_4 = str(st.user.mobile_number)[-4:]
        students_data.append({
            'name': f"{st.user.full_name} ({mobile_4})",
            'status': "Not Joined (Pending)",
            'score': "-",
            'color': 'yellow'
        })

    questions = test.questions.all()
    hardest_q_text = "अभी पर्याप्त डेटा नहीं"
    max_wrong = 0

    for q in questions:
        wrong_count = StudentAnswer.objects.filter(
            question=q, attempt__test=test
        ).exclude(selected_option=q.correct_answer).exclude(selected_option__isnull=True).exclude(
            selected_option='').count()

        if wrong_count > max_wrong:
            max_wrong = wrong_count
            q_index = list(questions).index(q) + 1
            hardest_q_text = f"Q{q_index}: {q.question_text[:40]}... <br><span style='color:#ff4c4c; font-size:12px;'>({wrong_count} बच्चों ने गलत किया)</span>"

    return JsonResponse({
        'joined_count': attempts.count(),
        'pending_count': pending_students.count(),
        'hardest_question': hardest_q_text,
        'students': students_data
    })


# 3. आंसर बदलना और रीकैलकुलेट करना
from django.shortcuts import redirect
from django.contrib import messages


@login_required
def update_answer_key(request, test_id):  # 🚀 यहाँ question_id की जगह test_id कर दिया है
    if request.method == 'POST':
        try:
            # URL से आ रही 1134 आईडी असल में प्रश्न की ID ही है
            # (अगर आपके मॉडल का नाम Question की जगह कुछ और है तो वही लिखें)
            question = Question.objects.get(id=test_id)

            new_answer = request.POST.get('correct_answer')
            if new_answer:
                question.correct_answer = new_answer
                question.save()
                messages.success(request, '✅ उत्तर सफलतापूर्वक बदल दिया गया है!')

        except Exception as e:
            messages.error(request, '❌ यह प्रश्न नहीं मिला या कोई एरर आ गया!')

        # शिक्षक को वापस उसी प्रीव्यू पेज पर रिडायरेक्ट करें
        return redirect(request.META.get('HTTP_REFERER', 'teacher_dashboard'))



@login_required
def choose_questions(request):
    if request.user.role != 'TEACHER':
        return redirect('home')

    # ---------------------------------------------------------
    # 🚀 1. AJAX Server-Side Pagination & Smart Search Logic
    # ---------------------------------------------------------
    if request.GET.get('ajax') == '1':
        cat_id = request.GET.get('category', 'ALL')
        sub_id = request.GET.get('subject', 'ALL')
        chap_id = request.GET.get('chapter', 'ALL')
        search_text = request.GET.get('search', '').strip()
        page_num = request.GET.get('page', 1)

        # सारे प्रश्न मंगाएं (लेटेस्ट सबसे ऊपर)
        questions = GlobalQuestionBank.objects.all().order_by('-created_at')

        # Filters Apply करें
        if cat_id != 'ALL':
            questions = questions.filter(category_id=cat_id)
        if sub_id != 'ALL':
            questions = questions.filter(subcategory_id=sub_id)
        if chap_id != 'ALL':
            questions = questions.filter(chapter_id=chap_id)

        # Smart Search (कम से कम 3 अक्षर होने पर ही डेटाबेस सर्च करेगा)
        if len(search_text) >= 3:
            questions = questions.filter(
                Q(question_text__icontains=search_text) |
                Q(option_a__icontains=search_text) |
                Q(option_b__icontains=search_text) |
                Q(option_c__icontains=search_text) |
                Q(option_d__icontains=search_text)
            )

        # Pagination (एक बार में सिर्फ़ 20 सवाल)
        paginator = Paginator(questions, 20)
        page_obj = paginator.get_page(page_num)

        # JSON डेटा तैयार करें
        data = []
        for q in page_obj:
            data.append({
                'id': q.id,
                'question_text': q.question_text,
                'category': q.category.name if getattr(q, 'category', None) else '',
                'subcategory': q.subcategory.name if getattr(q, 'subcategory', None) else '',
                'chapter': q.chapter.name if getattr(q, 'chapter', None) else '',
                'option_a': q.option_a,
                'option_b': q.option_b,
                'option_c': q.option_c,
                'option_d': q.option_d,
                'correct_answer': q.correct_answer,
            })

        return JsonResponse({
            'questions': data,
            'has_next': page_obj.has_next(),
            'total_results': paginator.count
        })

    # ---------------------------------------------------------
    # 🚀 2. Initial Page Load (जब पेज पहली बार खुलेगा)
    # ---------------------------------------------------------
    categories = QuestionCategory.objects.all()
    subcategories = QuestionSubCategory.objects.all()
    chapters = QuestionChapter.objects.all()

    draft_tests = MockTest.objects.filter(teacher=request.user.teacher_profile, status='DRAFT')

    return render(request, 'portal/choose_questions.html', {
        'categories': categories,
        'subcategories': subcategories,
        'chapters': chapters,
        'draft_tests': draft_tests
        # 'questions' को यहाँ से हटा दिया गया है क्योंकि अब यह JS द्वारा बैकग्राउंड (AJAX) में लोड होगा
    })


@login_required
def api_add_bank_questions(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            test_id = data.get('test_id')
            q_ids = data.get('q_ids', [])

            if not q_ids:
                return JsonResponse({'status': 'error', 'message': 'कोई प्रश्न सेलेक्ट नहीं किया गया है!'})

            if test_id:
                test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
            else:
                title = data.get('title')
                code = data.get('test_code').upper().strip()
                time = data.get('total_time', 10)
                pos = data.get('correct_marks', 4)
                neg = data.get('negative_marks', 1)

                if MockTest.objects.filter(test_code=code).exists():
                    return JsonResponse(
                        {'status': 'error', 'message': f'टेस्ट कोड "{code}" पहले से मौजूद है! नया कोड डालें।'})

                test = MockTest.objects.create(
                    teacher=request.user.teacher_profile, title=title, test_code=code,
                    total_time=time, correct_marks=pos, negative_marks=neg, status='DRAFT'
                )

            global_qs = GlobalQuestionBank.objects.filter(id__in=q_ids)
            for gq in global_qs:
                Question.objects.create(
                    test=test, question_text=gq.question_text, option_a=gq.option_a,
                    option_b=gq.option_b, option_c=gq.option_c, option_d=gq.option_d,
                    correct_answer=gq.correct_answer, explanation=gq.explanation
                )

            return JsonResponse(
                {'status': 'success', 'message': f'🎉 {len(q_ids)} प्रश्न सफलतापूर्वक "{test.title}" में जुड़ गए हैं!'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid Request'})


@login_required
def delete_single_question(request, q_id):
    if request.user.role != 'TEACHER':
        return redirect('home')
    try:
        question = Question.objects.get(id=q_id, test__teacher=request.user.teacher_profile)
        test_id = question.test.id
        question.delete()
        messages.success(request, '🗑️ प्रश्न सफलतापूर्वक हटा दिया गया है!')
        return redirect('preview_test', test_id=test_id)
    except Question.DoesNotExist:
        messages.error(request, 'प्रश्न नहीं मिला!')
        return redirect('teacher_dashboard')


@login_required
def test_instructions(request, test_id):
    test = MockTest.objects.get(id=test_id)

    attempt, created = TestAttempt.objects.get_or_create(
        student=request.user.student_profile,
        test=test
    )

    is_early = False
    formatted_time = ""

    if test.scheduled_time:
        now = timezone.now()
        if now < test.scheduled_time:
            is_early = True
            local_scheduled_time = timezone.localtime(test.scheduled_time)
            formatted_time = local_scheduled_time.strftime("%d %b, %I:%M %p")

    if request.method == 'POST':
        if is_early:
            messages.error(request, f'⏳ कृपया प्रतीक्षा करें! यह टेस्ट {formatted_time} पर शुरू होगा।')
            return redirect('test_instructions', test_id=test.id)

        return redirect('take_test', attempt_id=attempt.id)

    return render(request, 'portal/instructions.html', {
        'test': test,
        'is_early': is_early,
        'formatted_time': formatted_time
    })


@login_required
def api_active_students(request, test_id):
    attempts = TestAttempt.objects.filter(test_id=test_id).select_related('student__user')

    students_data = []
    for attempt in attempts:
        mobile_4 = str(attempt.student.user.mobile_number)[-4:]
        name = f"{attempt.student.user.full_name} ({mobile_4})"

        if attempt.is_completed:
            status = "Submitted 🏁"
            color = "#ffc107"
        else:
            status = "Waiting / Live 🟢"
            color = "#00ff00"

        students_data.append({'name': name, 'status': status, 'color': color})

    return JsonResponse({
        'count': attempts.count(),
        'students': students_data
    })


# ==========================================
# 🚀 RAZORPAY PAYMENT VIEWS
# ==========================================

@login_required
def initiate_payment(request):
    if request.user.role != 'STUDENT':
        return redirect('home')

    student = request.user.student_profile
    coaching = student.enrolled_coaching

    # 1. फीस तय करना (अगर कोचिंग है तो उसकी फीस, वरना डिफ़ॉल्ट ₹99)
    fee_amount = coaching.subscription_fee if coaching else 99.00
    amount_in_paise = int(fee_amount * 100)  # Razorpay पैसे (paise) में अमाउंट लेता है

    # 2. Razorpay पर Order बनाना
    currency = "INR"
    razorpay_order = razorpay_client.order.create(dict(
        amount=amount_in_paise,
        currency=currency,
        payment_capture='0'
    ))
    razorpay_order_id = razorpay_order['id']

    # 3. डेटाबेस में Transaction Pending के रूप में सेव करना
    PaymentTransaction.objects.create(
        user=request.user,
        payment_type='SUBSCRIPTION',
        amount=fee_amount,
        razorpay_order_id=razorpay_order_id,
        status='PENDING'
    )

    context = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_merchant_key': settings.RAZORPAY_KEY_ID,
        'razorpay_amount': amount_in_paise,
        'currency': currency,
        'fee_amount': fee_amount,
        'student': student,
    }

    return render(request, 'portal/payment_page.html', context)


@csrf_exempt
def verify_payment(request):
    if request.method == "POST":
        payment_id = request.POST.get('razorpay_payment_id', '')
        order_id = request.POST.get('razorpay_order_id', '')
        signature = request.POST.get('razorpay_signature', '')

        try:
            transaction = PaymentTransaction.objects.get(razorpay_order_id=order_id)
        except PaymentTransaction.DoesNotExist:
            return JsonResponse({'status': 'Failed', 'message': 'Transaction not found'})

        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }

        try:
            razorpay_client.utility.verify_payment_signature(params_dict)

            transaction.razorpay_payment_id = payment_id
            transaction.razorpay_signature = signature
            transaction.status = 'SUCCESS'
            transaction.save()

            # 🚀 1. अगर यह सब्सक्रिप्शन का पेमेंट है:
            if transaction.payment_type == 'SUBSCRIPTION':
                student = transaction.user.student_profile
                coaching = student.enrolled_coaching
                validity_days = coaching.subscription_validity_days if coaching else 30

                if student.subscription_expiry_date and student.subscription_expiry_date > timezone.now():
                    student.subscription_expiry_date += timedelta(days=validity_days)
                else:
                    student.subscription_expiry_date = timezone.now() + timedelta(days=validity_days)
                student.save()

                if coaching:
                    admin_comm = coaching.admin_commission
                    teacher_share = transaction.amount - admin_comm
                    coaching.wallet_balance += teacher_share
                    coaching.save()
                    WalletTransaction.objects.create(
                        user=coaching.user, transaction_type='CREDIT',
                        amount=teacher_share, description=f"Student {student.display_name} purchased subscription"
                    )

                messages.success(request, f"Payment Successful! आपका {validity_days} दिन का प्लान एक्टिवेट हो गया है।")
                return redirect('home')

            # 🚀 2. अगर यह वॉलेट रिचार्ज है:
            elif transaction.payment_type == 'WALLET_RECHARGE':
                profile = transaction.user.student_profile if transaction.user.role == 'STUDENT' else transaction.user.teacher_profile
                profile.wallet_balance += transaction.amount
                profile.save()

                WalletTransaction.objects.create(
                    user=transaction.user, transaction_type='CREDIT',
                    amount=transaction.amount, description="Online Wallet Recharge via Razorpay"
                )
                messages.success(request, f"₹{transaction.amount} आपके वॉलेट में सफलता से जुड़ गए हैं!")
                return redirect('wallet_dashboard')

        except razorpay.errors.SignatureVerificationError:
            transaction.status = 'FAILED'
            transaction.save()
            messages.error(request, "Payment Failed or tampered. Please try again.")
            return redirect('home')

    return redirect('home')

# ==========================================
# 🚀 WALLET PAYMENT VIEW
# ==========================================
@login_required
def pay_via_wallet(request):
    if request.user.role != 'STUDENT':
        return redirect('home')

    student = request.user.student_profile
    coaching = student.enrolled_coaching

    # 1. फीस तय करना
    fee_amount = coaching.subscription_fee if coaching else Decimal('99.00')

    # 2. चेक करना कि क्या वॉलेट में पर्याप्त बैलेंस है?
    if student.wallet_balance >= fee_amount:
        # --- 🚀 पेमेंट सक्सेसफुल (वॉलेट से) ---

        # स्टूडेंट के वॉलेट से पैसे काटना
        student.wallet_balance -= fee_amount

        # 3. छात्र का सब्सक्रिप्शन चालू करना
        validity_days = coaching.subscription_validity_days if coaching else 30
        if student.subscription_expiry_date and student.subscription_expiry_date > timezone.now():
            student.subscription_expiry_date += timedelta(days=validity_days)
        else:
            student.subscription_expiry_date = timezone.now() + timedelta(days=validity_days)

        student.save()

        # स्टूडेंट की पासबुक में एंट्री (Debit)
        WalletTransaction.objects.create(
            user=request.user,
            transaction_type='DEBIT',
            amount=fee_amount,
            description=f"Subscription purchased for {validity_days} days via Wallet"
        )

        # 4. पैसे का बँटवारा (Revenue Split)
        if coaching:
            admin_comm = coaching.admin_commission
            teacher_share = fee_amount - admin_comm

            # टीचर के वॉलेट में पैसा जोड़ें
            coaching.wallet_balance += teacher_share
            coaching.save()

            # टीचर की पासबुक में एंट्री (Credit)
            WalletTransaction.objects.create(
                user=coaching.user,
                transaction_type='CREDIT',
                amount=teacher_share,
                description=f"Student {student.display_name} purchased subscription via Wallet"
            )

        messages.success(request,
                         f"🎉 शानदार! आपके वॉलेट से ₹{fee_amount} कट गए हैं और आपका {validity_days} दिन का प्लान एक्टिवेट हो गया है।")
        return redirect('home')

    else:
        # अगर वॉलेट में पैसे कम हैं
        messages.error(request, "❌ आपके वॉलेट में पर्याप्त बैलेंस नहीं है। कृपया ऑनलाइन पेमेंट करें।")
        return redirect('initiate_payment')


# ==========================================
# 🚀 WALLET DASHBOARD & ADD MONEY
# ==========================================
@login_required
def wallet_dashboard(request):
    # पासबुक की हिस्ट्री लाना
    transactions = WalletTransaction.objects.filter(user=request.user).order_by('-created_at')
    context = {'transactions': transactions}

    if request.user.role == 'STUDENT':
        student = request.user.student_profile
        context['balance'] = student.wallet_balance
        context['is_student'] = True

        # एक्सपायरी डेट कैलकुलेट करना
        now = timezone.now()
        if student.subscription_expiry_date and student.subscription_expiry_date > now:
            context['plan_status'] = 'Active (Paid Plan)'
            context['expiry_date'] = student.subscription_expiry_date
        elif student.trial_expiry_date and student.trial_expiry_date > now:
            context['plan_status'] = 'Active (Free Trial)'
            context['expiry_date'] = student.trial_expiry_date
        else:
            context['plan_status'] = 'Expired'
            context['expiry_date'] = None

    elif request.user.role == 'TEACHER':
        teacher = request.user.teacher_profile
        context['balance'] = teacher.wallet_balance
        context['is_teacher'] = True
    else:
        return redirect('home')

    return render(request, 'portal/wallet_dashboard.html', context)


@login_required
def add_money(request):
    if request.method == 'POST':
        amount = float(request.POST.get('amount', 0))
        if amount < 10:
            messages.error(request, 'कम से कम ₹10 ऐड करें।')
            return redirect('wallet_dashboard')

        amount_in_paise = int(amount * 100)

        # Razorpay आर्डर बनाना
        razorpay_order = razorpay_client.order.create(dict(
            amount=amount_in_paise, currency="INR", payment_capture='0'
        ))

        # डेटाबेस में एंट्री
        PaymentTransaction.objects.create(
            user=request.user, payment_type='WALLET_RECHARGE',
            amount=amount, razorpay_order_id=razorpay_order['id'], status='PENDING'
        )

        # 🚀 NEW: कॉन्टेक्स्ट तैयार करना
        context = {
            'razorpay_order_id': razorpay_order['id'],
            'razorpay_merchant_key': settings.RAZORPAY_KEY_ID,
            'razorpay_amount': amount_in_paise,
            'currency': "INR",
            'fee_amount': amount,
            'is_recharge': True  # इससे पेज को पता चलेगा कि यह वॉलेट रिचार्ज है
        }

        # 🚀 NEW: रोल के हिसाब से प्रोफाइल भेजना
        if request.user.role == 'STUDENT':
            context['student'] = request.user.student_profile
        elif request.user.role == 'TEACHER':
            context['teacher'] = request.user.teacher_profile

        return render(request, 'portal/payment_page.html', context)
    return redirect('wallet_dashboard')


# ==========================================
# 🚀 WITHDRAWAL REQUEST VIEW (पूरा कोड)
# ==========================================
@login_required
def request_withdrawal(request):
    if request.method == 'POST':
        amount_str = request.POST.get('amount', 0)
        payment_method = request.POST.get('payment_method')

        # 🚀 NEW: डायनामिक बॉक्स से डेटा उठाना और जोड़ना
        if payment_method == 'BANK':
            acc_no = request.POST.get('account_number')
            ifsc = request.POST.get('ifsc_code')
            payment_details = f"A/C: {acc_no} | IFSC: {ifsc}"
        else:
            payment_details = request.POST.get('upi_id')

        try:
            amount = Decimal(str(amount_str))
        except:
            messages.error(request, 'अमान्य राशि (Invalid Amount)।')
            return redirect('wallet_dashboard')

        # यूज़र की प्रोफाइल पता करना
        if request.user.role == 'TEACHER':
            profile = request.user.teacher_profile
        elif request.user.role == 'STUDENT':
            profile = request.user.student_profile
        else:
            return redirect('home')

        # नियम 1: कम से कम ₹100 निकाल सकते हैं
        if amount < Decimal('100'):
            messages.error(request, '❌ आप कम से कम ₹100 निकाल सकते हैं।')
            return redirect('wallet_dashboard')

        # नियम 2: वॉलेट में पैसा होना चाहिए
        if amount > profile.wallet_balance:
            messages.error(request, '❌ आपके वॉलेट में पर्याप्त बैलेंस नहीं है।')
            return redirect('wallet_dashboard')

        # 🚀 1. पैसे को वॉलेट से तुरंत काट लें (ताकि कोई डबल रिक्वेस्ट न कर सके)
        profile.wallet_balance -= amount
        profile.save()

        # 🚀 2. रिक्वेस्ट को डेटाबेस में सेव करें
        WithdrawalRequest.objects.create(
            user=request.user,
            amount=amount,
            payment_method=payment_method,
            payment_details=payment_details,
            status='PENDING'
        )

        # 🚀 3. पासबुक में एंट्री करें
        WalletTransaction.objects.create(
            user=request.user,
            transaction_type='DEBIT',
            amount=amount,
            description=f"Withdrawal Request via {payment_method} (Pending)"
        )

        messages.success(request, f'✅ शानदार! आपकी ₹{amount} निकालने की रिक्वेस्ट सफलता से सबमिट हो गई है। एडमिन इसे 24-48 घंटों में अप्रूव कर देंगे।')

    return redirect('wallet_dashboard')


# ==========================================
# 🚀 FORGOT PASSWORD VIEWS
# ==========================================

def forgot_password_view(request):
    if request.method == 'POST':
        # 1. ईमेल से फालतू स्पेस (Space) हटाना
        email = request.POST.get('email', '').strip()
        print(f"\n--- DEBUG: Forgot Password Request ---")
        print(f"DEBUG: User entered Email: '{email}'")

        # 2. चेक करें कि क्या इस ईमेल से कोई यूज़र है? (iexact कैपिटल/स्मॉल का फर्क मिटा देता है)
        try:
            user = CustomUser.objects.get(email__iexact=email)
            print(f"DEBUG: Success! User found: {user.full_name}")
        except CustomUser.DoesNotExist:
            print(f"DEBUG: Failed! No user exists with this email.")
            messages.error(request, 'यह ईमेल हमारे सिस्टम में रजिस्टर नहीं है। कृपया सही ईमेल डालें।')
            return redirect('forgot_password')

        # 3. OTP जनरेट करें
        reset_otp = str(random.randint(100000, 999999))
        print(f"DEBUG: Generated OTP: {reset_otp}")

        # 4. Session में ईमेल और OTP सेव करें
        request.session['reset_email'] = user.email  # डेटाबेस वाला असली ईमेल सेव करें
        request.session['reset_otp'] = reset_otp

        # 5. ईमेल पर OTP भेजें
        print(f"DEBUG: Sending email now...")
        send_mail(
            'KBC Portal - Password Reset OTP',
            f'आपका पासवर्ड रिसेट करने का OTP है: {reset_otp}\nकृपया इसे किसी के साथ शेयर न करें।',
            'admin@kbcportal.com',
            [user.email],
            fail_silently=False,
        )
        print(f"DEBUG: Email successfully sent to terminal!")

        messages.success(request, 'आपके ईमेल पर एक 6-अंकों का OTP भेजा गया है।')
        return redirect('verify_reset_otp')

    return render(request, 'portal/forgot_password.html')

def verify_reset_otp_view(request):
    # अगर सेशन में ईमेल नहीं है, तो वापस भेज दें (Security Check)
    if 'reset_email' not in request.session:
        return redirect('forgot_password')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        saved_otp = request.session.get('reset_otp')

        if entered_otp == saved_otp:
            # OTP सही है, अब यूज़र को नया पासवर्ड सेट करने की परमिशन दे दें
            request.session['reset_otp_verified'] = True
            messages.success(request, 'OTP वेरीफाई हो गया! कृपया अपना नया पासवर्ड बनाएं।')
            return redirect('reset_new_password')
        else:
            messages.error(request, 'OTP गलत है! कृपया सही OTP डालें।')

    return render(request, 'portal/verify_reset_otp.html')


def reset_new_password_view(request):
    # Security Check: क्या यूज़र ने OTP वेरीफाई किया है?
    if not request.session.get('reset_otp_verified'):
        messages.error(request, 'सुरक्षा कारणों से, कृपया पहले OTP वेरीफाई करें।')
        return redirect('forgot_password')

    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if new_password != confirm_password:
            messages.error(request, 'दोनों पासवर्ड मेल नहीं खा रहे हैं।')
            return redirect('reset_new_password')

        # डेटाबेस में पासवर्ड अपडेट करना
        email = request.session.get('reset_email')
        user = CustomUser.objects.get(email=email)

        user.set_password(new_password)  # यह पासवर्ड को सुरक्षित (Encrypt) करके सेव करता है
        user.save()

        # सुरक्षा के लिए सेशन से डेटा डिलीट कर दें
        del request.session['reset_email']
        del request.session['reset_otp']
        del request.session['reset_otp_verified']

        messages.success(request,
                         '🎉 बधाई हो! आपका पासवर्ड सफलतापूर्वक बदल गया है। अब आप नए पासवर्ड से लॉगिन कर सकते हैं।')
        return redirect('login')

    return render(request, 'portal/set_new_password.html')


@login_required
def upload_question_image(request, q_id):
    if request.user.role != 'TEACHER':
        return redirect('home')

    if request.method == 'POST' and request.FILES.get('image_file'):
        try:
            question = Question.objects.get(id=q_id, test__teacher=request.user.teacher_profile)

            # 🚀 1. प्रश्न का सही क्रम (Index) पता करना (जैसे Q4)
            all_questions = list(question.test.questions.all().order_by('id'))
            q_index = all_questions.index(question) + 1

            if question.question_image:
                question.question_image.delete(save=False)

            question.question_image = request.FILES['image_file']
            question.save()

            # 🚀 2. सही नंबर के साथ मैसेज दिखाना
            messages.success(request, f'✅ सफलता! Q{q_index} में इमेज जुड़ गई है।')

            # 🚀 3. पेज को उसी प्रश्न पर रोकने के लिए URL में # (Anchor) जोड़ना
            url = reverse('preview_test', args=[question.test.id])
            return redirect(f"{url}#question-{question.id}")

        except Question.DoesNotExist:
            messages.error(request, 'प्रश्न नहीं मिला!')

    return redirect('teacher_dashboard')


@login_required
def delete_question_image(request, q_id):
    if request.user.role != 'TEACHER':
        return redirect('home')

    try:
        question = Question.objects.get(id=q_id, test__teacher=request.user.teacher_profile)

        # 🚀 1. प्रश्न का सही क्रम पता करना
        all_questions = list(question.test.questions.all().order_by('id'))
        q_index = all_questions.index(question) + 1

        if question.question_image:
            question.question_image.delete(save=True)
            messages.success(request, f'✅ सफलता! Q{q_index} से इमेज हटा दी गई है।')

        # 🚀 2. पेज को वापस उसी प्रश्न पर रोकना
        url = reverse('preview_test', args=[question.test.id])
        return redirect(f"{url}#question-{question.id}")

    except Question.DoesNotExist:
        messages.error(request, 'प्रश्न नहीं मिला!')
        return redirect('teacher_dashboard')


@login_required
def profile_view(request):
    user = request.user

    if request.method == 'POST':
        # 1. नया नाम प्राप्त करें
        new_name = request.POST.get('full_name')

        if new_name:
            # यूज़र के मुख्य अकाउंट में नाम सेव करें
            user.full_name = new_name
            user.save()

            # 🚀 NEW: अगर यूज़र स्टूडेंट है, तो डिस्प्ले नेम (Display Name) भी ऑटो-अपडेट करें
            if user.role == 'STUDENT':
                # मोबाइल नंबर के आखिरी 4 अंक निकालें (अगर नंबर नहीं है तो 0000)
                last_4_digits = str(user.mobile_number)[-4:] if user.mobile_number else "0000"

                # नया डिस्प्ले नेम बनाएं (जैसे: RAM को uppercase करके RAM_9992 बनाएगा)
                new_display_name = f"{new_name.strip().upper()}_{last_4_digits}"

                # स्टूडेंट प्रोफाइल में इसे सेव कर दें
                student_profile = user.student_profile
                student_profile.display_name = new_display_name
                student_profile.save()

        # 2. अगर यूज़र टीचर है, तो कोचिंग का नाम भी अपडेट करें
        if user.role == 'TEACHER':
            new_coaching = request.POST.get('coaching_name')
            if new_coaching:
                teacher_profile = user.teacher_profile
                teacher_profile.coaching_name = new_coaching
                teacher_profile.save()

        # 3. सक्सेस मैसेज दिखाएं
        messages.success(request, '✅ आपकी प्रोफाइल सफलतापूर्वक अपडेट हो गई है!')
        return redirect('profile')

    return render(request, 'portal/profile.html', {'user': user})


@login_required
def update_correct_answer(request, q_id):
    if request.user.role != 'TEACHER':
        return redirect('home')

    if request.method == 'POST':
        try:
            question = Question.objects.get(id=q_id, test__teacher=request.user.teacher_profile)
            new_answer = request.POST.get('correct_answer')

            # चेक करें कि उत्तर A, B, C या D में से ही हो
            if new_answer in ['A', 'B', 'C', 'D']:
                question.correct_answer = new_answer
                question.save()

                # प्रश्न का सही क्रम पता करना
                all_questions = list(question.test.questions.all().order_by('id'))
                q_index = all_questions.index(question) + 1

                messages.success(request, f'✅ सफलता! Q{q_index} का सही उत्तर बदल दिया गया है।')

            # पेज को वापस उसी प्रश्न पर रोकना
            url = reverse('preview_test', args=[question.test.id])
            return redirect(f"{url}#question-{question.id}")

        except Question.DoesNotExist:
            messages.error(request, 'प्रश्न नहीं मिला!')

    return redirect('teacher_dashboard')