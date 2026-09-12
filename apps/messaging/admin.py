from django.contrib import admin

from .models import Conversation, ConversationMember, Message, MessageAttachment


class ConversationMemberInline(admin.TabularInline):
    model = ConversationMember
    extra = 1


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'name', 'created_by', 'updated_at')
    list_filter = ('type',)
    inlines = [ConversationMemberInline]


admin.site.register(Message)
admin.site.register(MessageAttachment)