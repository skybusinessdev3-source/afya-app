from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User


def upload_attachment_path(instance, filename):
    """Nom de fichier sécurisé (§16.1 : nom sécurisé, emplacement contrôlé)."""
    import secrets
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return f"messaging/{instance.message.conversation_id}/{secrets.token_hex(8)}.{ext}"


class Conversation(TimeStampedModel):
    class Types(models.TextChoices):
        PRIVATE = 'PRIVATE', 'Privée'
        GROUP = 'GROUP', 'Groupe'

    type = models.CharField(max_length=10, choices=Types.choices, default=Types.PRIVATE)
    name = models.CharField(max_length=150, blank=True)  # obligatoire pour un groupe
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                   null=True, related_name='conversations_created')
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-updated_at']

    def clean(self):
        if self.type == self.Types.GROUP and not self.name:
            raise ValidationError("Un groupe doit avoir un nom.")

    def __str__(self):
        return self.name or f"Conversation privée #{self.pk}"

    def is_member(self, user):
        return self.members.filter(user=user, is_active=True).exists()

    def assert_member(self, user):
        """À appeler dans CHAQUE vue/service — §16.1."""
        if not self.is_member(user):
            raise PermissionError("Vous n'appartenez pas à cette conversation.")

    def last_message(self):
        return self.messages.select_related('sender').first()


class ConversationMember(TimeStampedModel):
    class Roles(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrateur'
        MEMBER = 'MEMBER', 'Membre'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversation_memberships')
    role = models.CharField(max_length=10, choices=Roles.choices, default=Roles.MEMBER)
    is_active = models.BooleanField(default=True)  # quitte le groupe ≠ suppression de l'historique
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('conversation', 'user')

    def __str__(self):
        return f"{self.user} dans {self.conversation}"


class Message(TimeStampedModel):
    """Message texte — les pièces jointes sont dans MessageAttachment."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='messages_sent')
    content = models.TextField(blank=True)  # vide si message vocal/pièce jointe seule
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='replies')
    # Mise en forme légère (gras/italique/listes seront stockés en HTML sanitizé — à voir au frontend)
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)  # suppression "pour tous" = flag, pas de perte de données
    # Messagerie éphémère : le message disparaît de l'interface après X heures
    ephemeral_hours = models.PositiveSmallIntegerField(null=True, blank=True,
                                                       verbose_name="Disparaît après (heures)")

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['conversation', '-created_at'])]

    @property
    def is_visible(self):
        """False si le message éphémère a expiré (filtré côté requêtes/vues)."""
        if self.ephemeral_hours:
            return timezone.now() < self.created_at + timezone.timedelta(hours=self.ephemeral_hours)
        return True

    def delete_for_all(self):
        self.is_deleted = True
        self.content = ''
        self.save(update_fields=['is_deleted', 'content'])

    def __str__(self):
        preview = (self.content or '[pièce jointe]')[:40]
        return f"{self.sender} : {preview}"


class MessageAttachment(TimeStampedModel):
    """Fichier joint : image, vidéo, audio (vocal), document."""

    class Types(models.TextChoices):
        IMAGE = 'IMAGE', 'Image'
        VIDEO = 'VIDEO', 'Vidéo'
        AUDIO = 'AUDIO', 'Audio / vocal'
        DOCUMENT = 'DOCUMENT', 'Document'

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=upload_attachment_path)
    file_type = models.CharField(max_length=10, choices=Types.choices)
    original_name = models.CharField(max_length=255, blank=True)
    size = models.PositiveIntegerField(default=0, help_text="Taille en octets")
    duration = models.PositiveIntegerField(null=True, blank=True, help_text="Durée en secondes (audio/vidéo)")

    MAX_SIZE = 25 * 1024 * 1024  # 25 Mo — ajustable
    ALLOWED_MIME = {
        Types.IMAGE: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
        Types.VIDEO: ['video/mp4', 'video/webm'],
        Types.AUDIO: ['audio/mpeg', 'audio/ogg', 'audio/webm', 'audio/wav'],
        Types.DOCUMENT: ['application/pdf', 'text/plain',
                         'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    }

    def clean(self):
        if self.size > self.MAX_SIZE:
            raise ValidationError("Fichier trop volumineux (max 25 Mo).")

    def __str__(self):
        return f"{self.get_file_type_display()} — {self.original_name or self.file.name}"