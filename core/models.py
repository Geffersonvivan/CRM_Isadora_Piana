from django.core.cache import cache
from django.db import models


class Configuracao(models.Model):
    """Configurações globais do CRM — registro único, editável pelo admin."""

    meta_votos = models.PositiveIntegerField('Meta de votos', default=45000)
    meta_doacoes = models.PositiveIntegerField('Meta de doações (R$)', default=120000)

    class Meta:
        verbose_name = 'Configuração'
        verbose_name_plural = 'Configurações'

    def __str__(self):
        return 'Configurações do CRM'

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)
        cache.delete('configuracao_crm')

    @classmethod
    def get(cls):
        config = cache.get('configuracao_crm')
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set('configuracao_crm', config, 300)
        return config
