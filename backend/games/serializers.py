from rest_framework import serializers

from games.models import Category, Game


def _reject_case_insensitive_duplicate(model, value, instance, label):
    name = value.strip()
    qs = model.objects.filter(name__iexact=name)
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise serializers.ValidationError(f'A {label} with this name already exists.')
    return name


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']

    def validate_name(self, value):
        return _reject_case_insensitive_duplicate(Category, value, self.instance, 'category')


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

    def validate_name(self, value):
        return _reject_case_insensitive_duplicate(Game, value, self.instance, 'game')

    def get_logo_url(self, obj):
        if obj.logo:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url
        return obj.cover_image_url or None
