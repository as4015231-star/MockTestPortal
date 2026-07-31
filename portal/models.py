from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager


# 1. कस्टम यूज़र मैनेजर
class CustomUserManager(BaseUserManager):
    def create_user(self, mobile_number, email, password=None, **extra_fields):
        if not mobile_number:
            raise ValueError('यूज़र का मोबाइल नंबर होना अनिवार्य है')
        if not email:
            raise ValueError('यूज़र का ईमेल होना अनिवार्य है')

        email = self.normalize_email(email)
        user = self.model(mobile_number=mobile_number, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')
        return self.create_user(mobile_number, email, password, **extra_fields)


# 2. कस्टम यूज़र मॉडल
class CustomUser(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('ADMIN', 'Super Admin'),
        ('TEACHER', 'Teacher'),
        ('OPERATOR', 'Data Operator'),
        ('STUDENT', 'Student'),
    )
    full_name = models.CharField(max_length=150)
    mobile_number = models.CharField(max_length=10, unique=True)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = ['email', 'full_name']
    last_session_key = models.CharField(max_length=40, null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.mobile_number})"


# 3. टीचर / कोचिंग प्रोफाइल
class TeacherProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='teacher_profile')
    coaching_code = models.CharField(max_length=10, unique=True)
    coaching_name = models.CharField(max_length=200)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return self.coaching_name


# 4. छात्र प्रोफाइल
class StudentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='student_profile')
    enrolled_coaching = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True)
    display_name = models.CharField(max_length=100, blank=True, null=True)
    is_super_student = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.display_name and self.user.full_name and self.user.mobile_number:
            first_name = self.user.full_name.split(" ")[0]
            last_4_digits = self.user.mobile_number[-4:]
            self.display_name = f"{first_name}_{last_4_digits}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name if self.display_name else self.user.full_name


# 5. मॉक टेस्ट मॉडल
class MockTest(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
    )
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='tests')
    title = models.CharField(max_length=200)
    test_code = models.CharField(max_length=15, unique=True)
    total_time = models.IntegerField(help_text="समय मिनटों में (उदा. 30)")
    correct_marks = models.DecimalField(max_digits=5, decimal_places=2, default=4.0)
    negative_marks = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    scheduled_time = models.DateTimeField(null=True, blank=True, help_text="टेस्ट शुरू होने का समय (वैकल्पिक)")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.test_code})"


# 6. प्रश्न मॉडल
class Question(models.Model):
    test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=1)
    explanation = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.question_text[:50]


# 7. टेस्ट ट्रैकिंग
class TestAttempt(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='attempts')
    test = models.ForeignKey(MockTest, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.student.display_name} - {self.test.title}"


# 8. छात्र के उत्तर
class StudentAnswer(models.Model):
    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, blank=True, null=True)

    def __str__(self):
        return f"{self.question.question_text[:20]} - {self.selected_option}"


# ==========================================
# --- 9. GLOBAL QUESTION BANK MODELS ---
# ==========================================
# ==========================================
# --- 9. GLOBAL QUESTION BANK MODELS ---
# ==========================================

class QuestionCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="e.g., Class 9, Class 10")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class QuestionSubCategory(models.Model):
    category = models.ForeignKey(QuestionCategory, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=100, help_text="e.g., Physics, Math")

    class Meta:
        unique_together = ('category', 'name')

    def __str__(self):
        return f"{self.category.name} - {self.name}"


# 🚀 NAYA MODEL: चैप्टर (Sub Category 2)
class QuestionChapter(models.Model):
    subcategory = models.ForeignKey(QuestionSubCategory, on_delete=models.CASCADE, related_name='chapters')
    name = models.CharField(max_length=150, help_text="e.g., Motion, Force and Laws of Motion")

    class Meta:
        unique_together = ('subcategory', 'name')

    def __str__(self):
        return f"{self.subcategory.category.name} - {self.subcategory.name} - {self.name}"


class GlobalQuestionBank(models.Model):
    category = models.ForeignKey(QuestionCategory, on_delete=models.CASCADE)
    subcategory = models.ForeignKey(QuestionSubCategory, on_delete=models.CASCADE)

    # 🚀 NAYA FIELD: चैप्टर लिंकिंग (null=True रखा है ताकि आपके पुराने 100 सवाल क्रैश न हों)
    chapter = models.ForeignKey(QuestionChapter, on_delete=models.SET_NULL, null=True, blank=True)

    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')])
    explanation = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question_text[:50] + "..."