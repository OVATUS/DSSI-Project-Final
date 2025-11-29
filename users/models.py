from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    created_at = models.DateTimeField(auto_now_add=True)
    profile_image = models.ImageField(
        upload_to = 'profile_images/',
        blank= True,
        null=True
    )

    def __str__(self):
        return self.username
    