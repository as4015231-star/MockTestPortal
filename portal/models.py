from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from datetime import timedelta


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

    # 🚀 NEW: Dynamic Pricing & Validation Fields (Admin Controls)
    subscription_fee = models.DecimalField(max_digits=10, decimal_places=2, default=99.00,
                                           help_text="छात्र से ली जाने वाली फीस")
    admin_commission = models.DecimalField(max_digits=10, decimal_places=2, default=49.00,
                                           help_text="इस फीस में एडमिन का हिस्सा")
    subscription_validity_days = models.IntegerField(default=30, help_text="यह पैकेज कितने दिन चलेगा?")

    def __str__(self):
        return self.coaching_name


# 4. छात्र प्रोफाइल
class StudentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='student_profile')
    enrolled_coaching = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True)
    display_name = models.CharField(max_length=100, blank=True, null=True)
    is_super_student = models.BooleanField(default=False)

    # 🚀 NEW: Wallet & Subscription Fields
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                         help_text="छात्र का वॉलेट बैलेंस (इनाम या रिचार्ज)")
    trial_expiry_date = models.DateTimeField(null=True, blank=True, help_text="72 घंटे का फ्री ट्रायल कब खत्म होगा")
    subscription_expiry_date = models.DateTimeField(null=True, blank=True,
                                                    help_text="पेमेंट वाला सब्सक्रिप्शन कब खत्म होगा")

    def save(self, *args, **kwargs):
        # 1. Display Name Logic (आपका पुराना लॉजिक)
        if not self.display_name and self.user.full_name and self.user.mobile_number:
            first_name = self.user.full_name.split(" ")[0]
            last_4_digits = self.user.mobile_number[-4:]
            self.display_name = f"{first_name}_{last_4_digits}"

        # 2. Auto 72-hour Trial Logic (नया लॉजिक)
        if not self.pk and not self.trial_expiry_date:
            self.trial_expiry_date = timezone.now() + timedelta(hours=72)

        super().save(*args, **kwargs)

    # 🚀 NEW: यह चेक करने के लिए कि बच्चा टेस्ट दे सकता है या नहीं
    def has_active_plan(self):
        now = timezone.now()
        # 1. क्या ट्रायल एक्टिव है?
        if self.trial_expiry_date and now <= self.trial_expiry_date:
            return True
        # 2. क्या सब्सक्रिप्शन एक्टिव है?
        if self.subscription_expiry_date and now <= self.subscription_expiry_date:
            return True
        return False

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
    question_image = models.ImageField(upload_to='question_images/', blank=True, null=True)

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


# ==========================================
# 🚀 10. RAZORPAY PAYMENT TRANSACTION MODEL
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

    # Razorpay Details
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.amount} - {self.status}"


# ==========================================
# 🚀 11. WALLET TRANSACTION MODEL (History)
# ==========================================
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


# ==========================================
# 🚀 12. WITHDRAWAL REQUEST MODEL
# ==========================================
class WithdrawalRequest(models.Model):  # <-- Fixed the capital 'M' here
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