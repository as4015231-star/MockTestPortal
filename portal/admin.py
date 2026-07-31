from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django import forms
import openpyxl
from django.contrib.auth.hashers import make_password  # 🚀 NAYA: पासवर्ड हैश करने के लिए

# एक ही जगह सारे मॉडल्स इम्पोर्ट कर लिए गए हैं
from .models import (
    CustomUser, TeacherProfile, StudentProfile,
    MockTest, Question,
    QuestionCategory, QuestionSubCategory, QuestionChapter, GlobalQuestionBank
)


# 1. कस्टम यूज़र को एडमिन पैनल में दिखाना
@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'mobile_number', 'email', 'role', 'is_active')
    search_fields = ('full_name', 'mobile_number', 'email')
    list_filter = ('role', 'is_active')

    # 🚀 FIX: एडमिन पैनल से पासवर्ड सेव करते समय उसे सुरक्षित तरीके से हैश (Encrypt) करना
    def save_model(self, request, obj, form, change):
        # अगर पासवर्ड मौजूद है और पहले से हैश नहीं किया गया है
        if obj.password and not obj.password.startswith('pbkdf2_'):
            obj.password = make_password(obj.password)
        super().save_model(request, obj, form, change)


# 2. टीचर/कोचिंग प्रोफाइल को एडमिन पैनल में दिखाना
@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('coaching_name', 'coaching_code', 'user', 'wallet_balance')
    search_fields = ('coaching_name', 'coaching_code', 'user__full_name')


# 3. छात्र प्रोफाइल को एडमिन पैनल में दिखाना
@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'enrolled_coaching', 'is_super_student')
    search_fields = ('display_name', 'user__mobile_number', 'user__full_name')
    list_filter = ('is_super_student', 'enrolled_coaching')


# 4. मॉक टेस्ट और प्रश्न
@admin.register(MockTest)
class MockTestAdmin(admin.ModelAdmin):
    list_display = ('title', 'test_code', 'teacher', 'status', 'created_at')
    list_filter = ('status', 'teacher')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'test', 'correct_answer')


# 5. क्वेश्चन कैटेगरी और सब-कैटेगरी
@admin.register(QuestionCategory)
class QuestionCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(QuestionSubCategory)
class QuestionSubCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category']
    list_filter = ['category']
    search_fields = ['name']


# 🚀 NAYA: Chapter Admin
@admin.register(QuestionChapter)
class QuestionChapterAdmin(admin.ModelAdmin):
    list_display = ['name', 'subcategory']
    list_filter = ['subcategory__category', 'subcategory']
    search_fields = ['name']


# ==========================================
# --- 6. EXCEL UPLOAD LOGIC FOR ADMIN ---
# ==========================================

# 🚀 FIX: फॉर्म में अब Chapter का फील्ड भी जोड़ दिया गया है
class ExcelUploadForm(forms.Form):
    category = forms.ModelChoiceField(queryset=QuestionCategory.objects.all(), label="1. Select Class")
    subcategory = forms.ModelChoiceField(queryset=QuestionSubCategory.objects.all(), label="2. Select Subject")
    chapter = forms.ModelChoiceField(queryset=QuestionChapter.objects.all(), label="3. Select Chapter")
    excel_file = forms.FileField(label="4. Upload Excel File")


@admin.register(GlobalQuestionBank)
class GlobalQuestionBankAdmin(admin.ModelAdmin):
    # 🚀 FIX: लिस्ट में chapter भी दिखेगा
    list_display = ['question_text', 'category', 'subcategory', 'chapter', 'correct_answer']
    list_filter = ['category', 'subcategory', 'chapter']
    search_fields = ['question_text']

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
                category = form.cleaned_data['category']
                subcategory = form.cleaned_data['subcategory']
                chapter = form.cleaned_data['chapter']
                excel_file = form.cleaned_data['excel_file']

                try:
                    wb = openpyxl.load_workbook(excel_file)
                    sheet = wb.active
                    count = 0
                    for row in sheet.iter_rows(min_row=2, values_only=True):
                        if not row[0]:
                            continue

                        GlobalQuestionBank.objects.create(
                            category=category,
                            subcategory=subcategory,
                            chapter=chapter,  # 🚀 NAYA: सवाल के साथ चैप्टर सेव हो रहा है
                            question_text=str(row[0]),
                            option_a=str(row[1]),
                            option_b=str(row[2]),
                            option_c=str(row[3]),
                            option_d=str(row[4]),
                            correct_answer=str(row[5]).strip().upper(),
                            explanation=str(row[6]) if len(row) > 6 and row[6] else ""
                        )
                        count += 1

                    self.message_user(request, f"✅ सफलता! {count} प्रश्न चैप्टर '{chapter.name}' में जोड़ दिए गए हैं।")
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