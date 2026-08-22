from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django import forms
import openpyxl
from django.contrib.auth.hashers import make_password

# 🚀 नए डेटाबेस डिज़ाइन के अनुसार सारे मॉडल्स इम्पोर्ट किए गए हैं
from .models import (
    CustomUser, TeacherProfile, StudentProfile,
    ExamCategory, SubjectCategory, ChapterCategory,
    MockTest, Question, TestQuestionMapping,
    TestAttempt, StudentAnswer,
    PaymentTransaction, WalletTransaction, WithdrawalRequest
)


# ==========================================
# 1. USERS & PROFILES
# ==========================================
@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'mobile_number', 'email', 'role', 'is_active')
    search_fields = ('full_name', 'mobile_number', 'email')
    list_filter = ('role', 'is_active')

    # एडमिन पैनल से पासवर्ड सेव करते समय उसे सुरक्षित तरीके से हैश (Encrypt) करना
    def save_model(self, request, obj, form, change):
        if obj.password and not obj.password.startswith('pbkdf2_'):
            obj.password = make_password(obj.password)
        super().save_model(request, obj, form, change)


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('coaching_name', 'coaching_code', 'user', 'wallet_balance')
    search_fields = ('coaching_name', 'coaching_code', 'user__full_name')


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'enrolled_coaching', 'is_super_student')
    search_fields = ('display_name', 'user__mobile_number', 'user__full_name')
    list_filter = ('is_super_student', 'enrolled_coaching')


# ==========================================
# 📂 2. THE 3-LAYER CATEGORY SYSTEM
# ==========================================
@admin.register(ExamCategory)
class ExamCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name']


@admin.register(SubjectCategory)
class SubjectCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'exam', 'created_by']
    list_filter = ['exam']
    search_fields = ['name']


@admin.register(ChapterCategory)
class ChapterCategoryAdmin(admin.ModelAdmin):
    # 👇 NAYA: sequence को लिस्ट में जोड़ दिया गया है
    list_display = ['name', 'subject', 'created_by', 'sequence']
    list_filter = ['subject__exam', 'subject']
    search_fields = ['name']

    # 👇 NAYA: अब आप एडमिन पैनल की लिस्ट से ही sequence एडिट कर पाएंगे
    list_editable = ['sequence']
    ordering = ['sequence']


# ==========================================
# 🏦 3. MASTER QUESTION BANK & EXCEL UPLOAD
# ==========================================

class ExcelUploadForm(forms.Form):
    exam = forms.ModelChoiceField(queryset=ExamCategory.objects.all(), label="1. Select Exam/Course")
    subject = forms.ModelChoiceField(queryset=SubjectCategory.objects.all(), label="2. Select Subject")
    chapter = forms.ModelChoiceField(queryset=ChapterCategory.objects.all(), label="3. Select Chapter")
    excel_file = forms.FileField(label="4. Upload Excel File")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    # 🌟 assigned_coaching से पता चलेगा कि प्रश्न प्राइवेट है या ग्लोबल
    list_display = ['question_text', 'chapter', 'assigned_coaching', 'correct_answer']
    list_filter = ['assigned_coaching', 'chapter__subject__exam', 'chapter__subject', 'chapter']
    search_fields = ['question_text']

    # आपका पुराना कस्टम टेम्प्लेट
    change_list_template = "admin/global_question_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload-excel/', self.admin_site.admin_view(self.upload_excel_view), name='upload_global_excel'),
        ]
        return custom_urls + urls

    def upload_excel_view(self, request):
        if request.method == 'POST':
            form = ExcelUploadForm(request.POST, request.FILES)
            if form.is_valid():
                chapter = form.cleaned_data['chapter']
                excel_file = form.cleaned_data['excel_file']

                try:
                    wb = openpyxl.load_workbook(excel_file)
                    sheet = wb.active
                    count = 0
                    for row in sheet.iter_rows(min_row=2, values_only=True):
                        if not row[0]:
                            continue

                        # 🚀 मैजिक: एडमिन द्वारा अपलोड किए गए प्रश्नों में assigned_coaching = None रहेगा (यानी ग्लोबल)
                        Question.objects.create(
                            chapter=chapter,
                            assigned_coaching=None,
                            question_text=str(row[0]),
                            option_a=str(row[1]),
                            option_b=str(row[2]),
                            option_c=str(row[3]),
                            option_d=str(row[4]),
                            correct_answer=str(row[5]).strip().upper(),
                            explanation=str(row[6]) if len(row) > 6 and row[6] else ""
                        )
                        count += 1

                    self.message_user(request, f"✅ सफलता! {count} ग्लोबल प्रश्न '{chapter.name}' में जोड़ दिए गए हैं।")
                    return redirect('..')
                except Exception as e:
                    self.message_user(request, f"❌ एरर: {str(e)}", level='error')
        else:
            form = ExcelUploadForm()

        context = dict(
            self.admin_site.each_context(request),
            form=form,
            title="Upload Global Questions via Excel"
        )
        return render(request, "admin/upload_global_excel.html", context)


# ==========================================
# 🛒 4. TESTS & SHOPPING CART
# ==========================================
@admin.register(MockTest)
class MockTestAdmin(admin.ModelAdmin):
    list_display = ('title', 'test_code', 'teacher', 'status', 'created_at')
    list_filter = ('status', 'teacher')


@admin.register(TestQuestionMapping)
class TestQuestionMappingAdmin(admin.ModelAdmin):
    list_display = ('test', 'question', 'order')
    list_filter = ('test',)


# ==========================================
# 🎯 5. TRACKING & ANSWERS
# ==========================================
@admin.register(TestAttempt)
class TestAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'test', 'is_completed', 'score', 'start_time')
    list_filter = ('is_completed',)


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'selected_option')


# ==========================================
# 🚀 6. PAYMENTS & WALLET
# ==========================================
@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'payment_type', 'amount', 'status', 'created_at')
    list_filter = ('status', 'payment_type')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'created_at')
    list_filter = ('transaction_type',)


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'status', 'payment_method', 'created_at')
    list_filter = ('status', 'payment_method')