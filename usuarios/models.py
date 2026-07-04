from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    PERFIL_CHOICES = [
        ('admin', 'Administrador'),
        ('coordenador', 'Coordenador'),
        ('lideranca', 'Liderança'),
        ('operador', 'Operador'),
    ]

    VINCULO_CHOICES = [
        ('coordenador', 'Coordenador'),
        ('cabo', 'Cabo Eleitoral'),
        ('replicador', 'Replicador'),
    ]

    perfil = models.CharField(max_length=20, choices=PERFIL_CHOICES, default='operador')
    vinculo = models.CharField(
        max_length=20, choices=VINCULO_CHOICES, blank=True,
        verbose_name='Vínculo na rede',
    )
    telefone = models.CharField(max_length=20, blank=True)
    regiao = models.ForeignKey(
        'liderancas.Regiao', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='usuarios',
    )
    foto = models.ImageField(upload_to='usuarios/fotos/', blank=True, null=True)
    cidade = models.ForeignKey(
        'liderancas.Cidade', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='usuarios',
    )
    instagram = models.CharField(max_length=100, blank=True)
    convidado_por = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='convidados',
        verbose_name='Convidado por',
    )

    secoes_permitidas = models.JSONField(
        default=list,
        blank=True,
        help_text='Lista de seções da sidebar que o usuário pode acessar',
    )
    areas_tarefas = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Áreas de tarefas',
        help_text='Setores cujas tarefas o usuário enxerga. Só as marcadas; '
                  'nenhuma marcada = não vê nenhuma tarefa. Admin sempre vê todas.',
    )

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return self.get_full_name() or self.username

    # Seções padrão sugeridas por perfil. NÃO é aplicado automaticamente no save
    # (vazio = nenhum acesso, por decisão explícita). É usado como sugestão ao
    # CRIAR pelo formulário (botão "Aplicar padrão do perfil") e pelo cadastro PWA.
    SECOES_PADRAO = {
        'admin': ['dashboard', 'demandas', 'equipes', 'liderancas', 'mapa', 'config'],
        'coordenador': ['dashboard', 'demandas', 'equipes', 'liderancas', 'mapa'],
        'lideranca': ['demandas', 'equipes', 'liderancas'],
        'operador': ['demandas', 'equipes'],
    }

    def get_secoes_padrao(self):
        return list(self.SECOES_PADRAO.get(self.perfil, []))

    def pode_acessar(self, secao):
        if self.perfil == 'admin':
            return True
        if secao in self.secoes_permitidas:
            return True
        # Acesso à seção pai dá acesso às sub-seções
        pai = secao.split(':')[0] if ':' in secao else None
        if pai and pai in self.secoes_permitidas:
            return True
        return False
