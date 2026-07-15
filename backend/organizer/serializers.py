from rest_framework import serializers

from organizer.models import Organizer


class OrganizerRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organizer
        fields = ['company_name', 'phone_number', 'address']


class OrganizerProfileSerializer(serializers.ModelSerializer):
    cnic_uploaded = serializers.SerializerMethodField()
    company_document_uploaded = serializers.SerializerMethodField()

    class Meta:
        model = Organizer
        fields = [
            'id', 'company_name', 'company_registration_number', 'phone_number', 'address',
            'cnic_number', 'cnic_document', 'company_document',
            'cnic_uploaded', 'company_document_uploaded',
            'status', 'rejection_reason', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'cnic_document', 'company_document',
            'status', 'rejection_reason', 'created_at', 'updated_at',
        ]

    def get_cnic_uploaded(self, obj):
        return bool(obj.cnic_document)

    def get_company_document_uploaded(self, obj):
        return bool(obj.company_document)


class OrganizerProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organizer
        fields = ['company_name', 'phone_number', 'address']


class OrganizerStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organizer
        fields = ['status', 'rejection_reason', 'updated_at']


class CnicUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organizer
        fields = ['cnic_number', 'cnic_document']
        extra_kwargs = {'cnic_document': {'required': True}}


class CompanyUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organizer
        fields = ['company_registration_number', 'company_document']
        extra_kwargs = {'company_document': {'required': True}}


class AdminOrganizerSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    cnic_uploaded = serializers.SerializerMethodField()
    company_document_uploaded = serializers.SerializerMethodField()

    class Meta:
        model = Organizer
        fields = [
            'id', 'user_id', 'user_email', 'company_name', 'company_registration_number',
            'phone_number', 'address', 'cnic_number', 'cnic_document', 'company_document',
            'cnic_uploaded', 'company_document_uploaded',
            'status', 'rejection_reason', 'created_at', 'updated_at',
        ]

    def get_cnic_uploaded(self, obj):
        return bool(obj.cnic_document)

    def get_company_document_uploaded(self, obj):
        return bool(obj.company_document)


class AdminOrganizerUpdateSerializer(serializers.ModelSerializer):
    reason = serializers.CharField(source='rejection_reason', required=False, allow_blank=True)

    class Meta:
        model = Organizer
        fields = ['status', 'reason']

    def update(self, instance, validated_data):
        if validated_data.get('status') == Organizer.Status.APPROVED and 'rejection_reason' not in validated_data:
            validated_data['rejection_reason'] = ''
        return super().update(instance, validated_data)
