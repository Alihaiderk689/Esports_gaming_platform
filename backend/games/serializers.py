from rest_framework import serializers

from games.models import Category, Game


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']


class GameSerializer(serializers.ModelSerializer):
    categories = CategorySerializer(many=True, read_only=True)
    category_ids = serializers.PrimaryKeyRelatedField(
        source='categories', queryset=Category.objects.all(), many=True, write_only=True, required=False,
    )
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            'id', 'name', 'slug', 'genre', 'platform', 'description',
            'cover_image_url', 'logo', 'logo_url', 'categories', 'category_ids',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
        extra_kwargs = {'logo': {'write_only': True}}

    def get_logo_url(self, obj):
        if obj.logo:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url
        return obj.cover_image_url or None
