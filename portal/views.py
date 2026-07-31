import random
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.mail import send_mail
import openpyxl
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.contrib.sessions.models import Session
import json

from .models import CustomUser, TeacherProfile, StudentProfile, MockTest, Question, TestAttempt, StudentAnswer, \
    QuestionCategory, QuestionSubCategory, QuestionChapter, GlobalQuestionBank


# 1. होम पेज
def home(request):
    return render(request, 'portal/home.html')


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
        total_score = 0
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

        total_score = (correct_answers * test.correct_marks) - (wrong_answers * test.negative_marks)

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
        score = 0
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

    # स्कोर के आधार पर घटते क्रम में सजाएं
    student_data.sort(key=lambda x: x['score'], reverse=True)

    # 🚀 FIX: DENSE RANKING LOGIC (समान अंक = समान रैंक)
    current_rank = 1
    previous_score = None

    for student in student_data:
        if previous_score is None:
            student['rank'] = current_rank
        elif student['score'] < previous_score:
            current_rank += 1
            student['rank'] = current_rank
        else:
            student['rank'] = current_rank  # Joint Rank

        previous_score = student['score']

    # रैंक को सीधे नाम के साथ जोड़ दें ताकि बिना HTML छेड़े स्कोरबोर्ड पर दिखने लगे
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

    # 1. सभी सबमिट किए हुए टेस्ट निकालें और स्कोर के हिसाब से घटते क्रम में लगाएं
    attempts = TestAttempt.objects.filter(test=test, is_completed=True).order_by('-score')

    winners = []
    highest_score = 0

    if attempts.exists():
        # अगर किसी कारण से स्कोर सेव नहीं हुआ है तो रनटाइम पर कैलकुलेट कर लें
        for attempt in attempts:
            if attempt.score is None:
                correct = sum(1 for ans in attempt.answers.all() if ans.selected_option == ans.question.correct_answer)
                wrong = sum(1 for ans in attempt.answers.all() if
                            ans.selected_option and ans.selected_option != ans.question.correct_answer)
                attempt.score = (correct * test.correct_marks) - (wrong * test.negative_marks)
                attempt.save(update_fields=['score'])

        # दोबारा रिफ्रेश्ड ऑर्डर
        attempts = TestAttempt.objects.filter(test=test, is_completed=True).order_by('-score')
        highest_score = attempts.first().score

        # 🚀 2. उस हाईएस्ट स्कोर वाले सभी बच्चों को निकालें (Joint Winners)
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

    # 1. सभी अटेम्प्ट्स निकालें स्कोर के घटते क्रम में
    attempts = TestAttempt.objects.filter(test=test, is_completed=True).order_by('-score')

    current_rank = 1
    previous_score = None
    student_attempt = None

    # 🚀 2. Dense Ranking लॉजिक से सबकी रैंक तय करें
    for attempt in attempts:
        if attempt.score is None:
            correct = sum(1 for ans in attempt.answers.all() if ans.selected_option == ans.question.correct_answer)
            wrong = sum(1 for ans in attempt.answers.all() if
                        ans.selected_option and ans.selected_option != ans.question.correct_answer)
            attempt.score = (correct * test.correct_marks) - (wrong * test.negative_marks)
            attempt.save(update_fields=['score'])

        if previous_score is None:
            attempt.rank = current_rank
        elif attempt.score < previous_score:
            current_rank += 1
            attempt.rank = current_rank
        else:
            attempt.rank = current_rank  # 🚀 Joint Rank

        previous_score = attempt.score

        # 3. जो बच्चा अभी देख रहा है, उसका डाटा अलग से छाँट लें ताकि सर्टिफिकेट में काम आ सके
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
@login_required
def update_answer_key(request, test_id):
    if request.user.role != 'TEACHER' or request.method != 'POST':
        return redirect('home')

    test = MockTest.objects.get(id=test_id, teacher=request.user.teacher_profile)
    question_id = request.POST.get('question_id')
    new_answer = request.POST.get('new_answer')

    question = Question.objects.get(id=question_id, test=test)
    question.correct_answer = new_answer
    question.save()

    attempts = TestAttempt.objects.filter(test=test, is_completed=True)
    for attempt in attempts:
        total_score = 0
        for ans in attempt.answers.all():
            if ans.selected_option:
                if ans.selected_option == ans.question.correct_answer:
                    total_score += test.correct_marks
                else:
                    total_score -= test.negative_marks
        attempt.score = total_score
        attempt.save()

    messages.success(request,
                     f'सफलता! Q{list(test.questions.all()).index(question) + 1} का उत्तर अपडेट हो गया और रिजल्ट बदल गया।')
    return redirect('live_test_monitor', test_id=test.id)


@login_required
def choose_questions(request):
    if request.user.role != 'TEACHER':
        return redirect('home')

    categories = QuestionCategory.objects.all()
    subcategories = QuestionSubCategory.objects.all()
    chapters = QuestionChapter.objects.all()

    questions = GlobalQuestionBank.objects.all().order_by('-created_at')[:2000]

    draft_tests = MockTest.objects.filter(teacher=request.user.teacher_profile, status='DRAFT')

    return render(request, 'portal/choose_questions.html', {
        'categories': categories,
        'subcategories': subcategories,
        'chapters': chapters,
        'questions': questions,
        'draft_tests': draft_tests
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

    # 🚀 FIX: जैसे ही बच्चा इंस्ट्रक्शन पेज (Waiting Lounge) पर आएगा,
    # हम उसकी एंट्री बना देंगे ताकि लाइव काउंट में उसका नाम तुरंत आ जाए!
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

        # चूँकि हम एंट्री पहले ही बना चुके हैं, इसलिए अब सीधे टेस्ट पेज पर भेजेंगे
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
            color = "#ffc107"  # Yellow
        else:
            # 🚀 FIX: जो बच्चे इंस्ट्रक्शन पेज पर हैं या टेस्ट दे रहे हैं, उन्हें यहाँ दिखाएंगे
            status = "Waiting / Live 🟢"
            color = "#00ff00"  # Green

        students_data.append({'name': name, 'status': status, 'color': color})

    return JsonResponse({
        'count': attempts.count(),
        'students': students_data
    })