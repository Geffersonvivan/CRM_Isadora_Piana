from django import forms
from core.forms import CidadePrimeiroFormMixin
from liderancas.models import Regiao, Cidade
from usuarios.models import Usuario
from .models import Tarefa, Comentario


class TarefaForm(CidadePrimeiroFormMixin, forms.ModelForm):
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all().order_by('sigla'),
        required=False,
        label='Região',
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
    )

    class Meta:
        model = Tarefa
        fields = [
            'titulo', 'descricao', 'tipo', 'prioridade',
            'responsavel', 'participantes',
            'regiao', 'cidade', 'prazo', 'link', 'link_reuniao', 'observacoes',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-input'}),
            'descricao': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'tipo': forms.Select(attrs={'class': 'form-input'}),
            'prioridade': forms.Select(attrs={'class': 'form-input'}),
            'responsavel': forms.Select(attrs={'class': 'form-input'}),
            'participantes': forms.SelectMultiple(attrs={'class': 'form-input', 'size': 5}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'prazo': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'link': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://… (documento, planilha, referência)'}),
            'link_reuniao': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://meet… / zoom… (link da videochamada)'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

    field_order = [
        'titulo', 'descricao', 'tipo', 'prioridade',
        'responsavel', 'participantes',
        'regiao', 'cidade', 'prazo', 'link', 'link_reuniao', 'observacoes',
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Aceita colar 'meet.google.com/...' sem esquema: prefixa https:// no dado
        # bruto ANTES da validação do URLField (mesma tolerância do inline na lista).
        if self.is_bound and self.data is not None:
            try:
                self.data = self.data.copy()   # QueryDict imutável → cópia mutável
            except AttributeError:
                self.data = dict(self.data)
            for campo in ('link', 'link_reuniao'):
                v = (self.data.get(campo) or '').strip()
                if v and not v.startswith(('http://', 'https://')):
                    self.data[campo] = 'https://' + v
        usuarios_sistema = Usuario.objects.exclude(
            vinculo__in=['coordenador', 'cabo', 'replicador']
        ).order_by('first_name')
        self.fields['responsavel'].queryset = usuarios_sistema
        self.fields['participantes'].queryset = usuarios_sistema

        # Usuário restrito a setores só pode criar/editar nas suas áreas.
        # Admin/superuser veem todas as opções.
        if user is not None and not (
            getattr(user, 'perfil', None) == 'admin' or getattr(user, 'is_superuser', False)
        ):
            areas = getattr(user, 'areas_tarefas', None) or []
            if areas:
                self.fields['tipo'].choices = [
                    (v, label) for v, label in Tarefa.AREA_CHOICES if v in areas
                ]
                if not self.instance.pk and self.initial.get('tipo') not in areas:
                    self.fields['tipo'].initial = areas[0]

        if self.instance.pk and self.instance.cidade_id:
            self.fields['regiao'].initial = self.instance.cidade.regiao_id
            self.fields['cidade'].queryset = Cidade.objects.filter(
                regiao=self.instance.cidade.regiao
            ).order_by('nome')
        else:
            regiao_id = self.data.get('regiao') if self.data else None
            if regiao_id:
                try:
                    self.fields['cidade'].queryset = Cidade.objects.filter(
                        regiao_id=int(regiao_id)
                    ).order_by('nome')
                except (ValueError, TypeError):
                    self.fields['cidade'].queryset = Cidade.objects.none()
            else:
                self.fields['cidade'].queryset = Cidade.objects.none()
        self.aplicar_cidade_primeiro()

    def clean(self):
        cleaned = super().clean()
        return self.derivar_regiao(cleaned)


class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto']
        widgets = {
            'texto': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 2,
                'placeholder': 'Escreva um comentário...',
            }),
        }

