from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from datetime import timedelta


# ==========================================
# 1. CUSTOM USER MANAGER & MODEL
# ==========================================
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


# ==========================================
# 2. PROFILES (TEACHER & STUDENT)
# ==========================================
class TeacherProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='teacher_profile')
    coaching_code = models.CharField(max_length=10, unique=True)
    coaching_name = models.CharField(max_length=200)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    subscription_fee = models.DecimalField(max_digits=10, decimal_places=2, default=99.00,
                                           help_text="छात्र से ली जाने वाली फीस")
    admin_commission = models.DecimalField(max_digits=10, decimal_places=2, default=49.00,
                                           help_text="इस फीस में एडमिन का हिस्सा")
    subscription_validity_days = models.IntegerField(default=30, help_text="यह पैकेज कितने दिन चलेगा?")

    demo_expiry_date = models.DateTimeField(null=True, blank=True,
                                            help_text="डेमो समाप्त होने की तारीख (एडमिन कंट्रोल)")

    def __str__(self):
        return self.coaching_name

    def is_demo_active(self):
        from django.utils import timezone
        if self.demo_expiry_date and timezone.now() <= self.demo_expiry_date:
            return True
        return False


class StudentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='student_profile')
    enrolled_coaching = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True)
    display_name = models.CharField(max_length=100, blank=True, null=True)
    is_super_student = models.BooleanField(default=False)

    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                         help_text="छात्र का वॉलेट बैलेंस")
    trial_expiry_date = models.DateTimeField(null=True, blank=True, help_text="72 घंटे का फ्री ट्रायल")
    subscription_expiry_date = models.DateTimeField(null=True, blank=True, help_text="पेमेंट वाला सब्सक्रिप्शन")

    def save(self, *args, **kwargs):
        if not self.display_name and self.user.full_name and self.user.mobile_number:
            first_name = self.user.full_name.split(" ")[0]
            last_4_digits = self.user.mobile_number[-4:]
            self.display_name = f"{first_name}_{last_4_digits}"

        if not self.pk and not self.trial_expiry_date:
            self.trial_expiry_date = timezone.now() + timedelta(hours=72)

        super().save(*args, **kwargs)

    def has_active_plan(self):
        now = timezone.now()
        if self.trial_expiry_date and now <= self.trial_expiry_date:
            return True
        if self.subscription_expiry_date and now <= self.subscription_expiry_date:
            return True
        return False

    def __str__(self):
        return self.display_name if self.display_name else self.user.full_name


# ==========================================
# 📂 3. THE 3-LAYER CATEGORY SYSTEM
# ==========================================
class ExamCategory(models.Model):
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_exams')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Exam Categories"


class SubjectCategory(models.Model):
    exam = models.ForeignKey(ExamCategory, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_subjects')

    def __str__(self):
        return f"{self.exam.name} - {self.name}"

    class Meta:
        verbose_name_plural = "Subject Categories"


class ChapterCategory(models.Model):
    subject = models.ForeignKey(SubjectCategory, on_delete=models.CASCADE, related_name='chapters')
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_chapters')

    # 👇 NAYA: Sequence field added for correct ordering
    sequence = models.IntegerField(default=0, help_text="चैप्टर का सही क्रम डालें (जैसे 1, 2, 3)")

    def __str__(self):
        return f"{self.subject.name} - {self.name}"

    class Meta:
        verbose_name_plural = "Chapter Categories"
        ordering = ['sequence']  # 👇 NAYA: This ensures chapters always show in correct order


# ==========================================
# 🏦 4. MASTER QUESTION BANK
# ==========================================
class Question(models.Model):
    chapter = models.ForeignKey(ChapterCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='questions')
    assigned_coaching = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, null=True, blank=True,
                                          related_name='private_questions')

    question_text = models.TextField()
    question_image = models.ImageField(upload_to='question_images/', blank=True, null=True)
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)

    # 👇 NAYA: Changed max_length to 255 to prevent varying(1) upload error
    correct_answer = models.CharField(max_length=255, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')])

    explanation = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q: {self.question_text[:40]}..."


# ==========================================
# 📝 5. MOCK TEST MODEL
# ==========================================
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


# ==========================================
# 🛒 6. TEST-QUESTION MAPPING
# ==========================================
class TestQuestionMapping(models.Model):
    test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='mapped_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0, help_text="प्रश्न का क्रम")

    class Meta:
        ordering = ['order']
        unique_together = ('test', 'question')

    def __str__(self):
        return f"{self.test.title} -> {self.question.id}"


# ==========================================
# 🎯 7. TEST TRACKING & STUDENT ANSWERS
# ==========================================
class TestAttempt(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='attempts')
    test = models.ForeignKey(MockTest, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.student.display_name} - {self.test.title}"


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, blank=True, null=True)

    def __str__(self):
        return f"{self.question.question_text[:20]} - {self.selected_option}"


# ==========================================
# 🚀 8. WALLET & PAYMENTS TRANSACTIONS
# ==========================================
class PaymentTransaction(models.Model):
    PAYMENT_TYPES = (
        ('SUBSCRIPTION', 'Test Subscription'),
        ('WALLET_RECHARGE', 'Wallet Recharge'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payments')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES, default='SUBSCRIPTION')
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.amount} - {self.status}"


class WalletTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('CREDIT', 'Credit (पैसे आए)'),
        ('DEBIT', 'Debit (पैसे कटे)'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='wallet_transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, help_text="उदा: इनाम मिला, सब्सक्रिप्शन खरीदा, या बैंक में निकाले")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} | {self.transaction_type} | ₹{self.amount}"


class WithdrawalRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending (लंबित)'),
        ('APPROVED', 'Approved (सफल)'),
        ('REJECTED', 'Rejected (रद्द)'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, choices=(('UPI', 'UPI ID'), ('BANK', 'Bank Account')),
                                      default='UPI')
    payment_details = models.CharField(max_length=255, help_text="अपना UPI ID या बैंक डिटेल्स यहाँ डालें")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_note = models.TextField(blank=True, null=True, help_text="अगर रिक्वेस्ट रिजेक्ट की है, तो उसका कारण")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} | ₹{self.amount} | {self.status}"