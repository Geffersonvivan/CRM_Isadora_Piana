from django import forms
from core.forms import CidadePrimeiroFormMixin
from .models import Usuario
from liderancas.models import Cidade, Regiao


SECOES_CHOICES = [
    # Dashboard
    ('dashboard', 'Dashboard'),
    ('dashboard:meta_votos', '— Meta Votos'),
    ('dashboard:relatorios', '— Relatórios'),
    # Demandas
    ('demandas', 'Demandas'),
    ('demandas:agenda', '— Agenda'),
    ('demandas:eventos', '— Eventos'),
    ('demandas:roteiros', '— Roteiros'),
    ('demandas:tarefas', '— Tarefas'),
    # Equipes
    ('equipes', 'Equipes'),
    ('equipes:mobilizacao', '— Mobilização'),
    ('equipes:aprovar', '— Aprovar voluntários do app'),
    # Lideranças
    ('liderancas', 'Lideranças'),
    ('liderancas:lista', '— Lideranças'),
    ('liderancas:aprovar', '— Aprovar leads do app'),
    # Mapa
    ('mapa', 'Mapa'),
    ('mapa:demandas', '— Demandas'),
    ('mapa:dep_aliados', '— Dep. Aliados'),
    ('mapa:eleicoes_2022', '— Eleições 2022'),
    ('mapa:estrategico', '— Estratégico'),
    ('mapa:mapa_calor', '— Mapa de Calor'),
    ('mapa:rede_pl', '— Rede NOVO'),
    ('mapa:regioes', '— Regiões'),
    ('mapa:roteiros', '— Roteiros'),
    ('mapa:transferencia', '— Transferência'),
    ('mapa:zonas_eleitorais', '— Zonas Eleitorais'),
    # Oportunidades
    ('oportunidades', 'Oportunidades'),
    ('oportunidades:territorio', '— Território'),
    ('oportunidades:relacionamento', '— Relacionamento'),
    ('oportunidades:concorrencia', '— Concorrência'),
    ('oportunidades:agenda', '— Agenda'),
    ('oportunidades:demandas', '— Demandas'),
    # Config
    ('config', 'Configurações'),
    ('config:usuarios', '— Usuários'),
]


AREAS_TAREFAS_CHOICES = [
    ('financeiro', 'Financeiro'),
    ('administrativo', 'Administrativo'),
    ('comunicacao', 'Comunicação'),
    ('mobilizacao', 'Mobilização'),
    ('estrategico', 'Estratégico'),
    ('eventos', 'Eventos'),
]


class UsuarioCreateForm(CidadePrimeiroFormMixin, forms.ModelForm):
    password1 = forms.CharField(label='Senha', widget=forms.PasswordInput(attrs={
        'class': 'form-input',
    }))
    password2 = forms.CharField(label='Confirmar senha', widget=forms.PasswordInput(attrs={
        'class': 'form-input',
    }))
    secoes = forms.MultipleChoiceField(
        choices=SECOES_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Seções permitidas',
    )
    areas = forms.MultipleChoiceField(
        choices=AREAS_TAREFAS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Áreas de tarefas',
    )

    class Meta:
        model = Usuario
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'perfil', 'telefone', 'regiao', 'cidade', 'foto',
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'perfil': forms.Select(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input'}),
            'regiao': forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'foto': forms.FileInput(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Perfil: apenas admin e operador
        self.fields['perfil'].choices = [
            ('admin', 'Administrador'),
            ('operador', 'Operador'),
        ]
        # Todos obrigatórios exceto foto e seções
        for name, field in self.fields.items():
            if name not in ('foto', 'secoes', 'areas', 'is_active'):
                field.required = True
                if hasattr(field.widget, 'attrs'):
                    field.widget.attrs['required'] = 'required'
        self.fields['regiao'].queryset = Regiao.objects.all().order_by('sigla')
        self.fields['regiao'].empty_label = '---------'
        if self.instance.pk and self.instance.regiao_id:
            self.fields['cidade'].queryset = Cidade.objects.filter(regiao=self.instance.regiao).order_by('nome')
        else:
            regiao_id = self.data.get('regiao') if self.data else None
            if regiao_id:
                try:
                    self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=int(regiao_id)).order_by('nome')
                except (ValueError, TypeError):
                    self.fields['cidade'].queryset = Cidade.objects.none()
            else:
                self.fields['cidade'].queryset = Cidade.objects.none()
        self.aplicar_cidade_primeiro()

    def clean(self):
        cleaned = super().clean()
        return self.derivar_regiao(cleaned)

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('As senhas não coincidem.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.secoes_permitidas = self.cleaned_data.get('secoes', [])
        user.areas_tarefas = self.cleaned_data.get('areas', [])
        if commit:
            user.save()
        return user


class UsuarioEditForm(CidadePrimeiroFormMixin, forms.ModelForm):
    password = forms.CharField(
        label='Nova senha (deixe em branco para manter)',
        widget=forms.PasswordInput(attrs={'class': 'form-input'}),
        required=False,
    )
    secoes = forms.MultipleChoiceField(
        choices=SECOES_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Seções permitidas',
    )
    areas = forms.MultipleChoiceField(
        choices=AREAS_TAREFAS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Áreas de tarefas',
    )

    class Meta:
        model = Usuario
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'perfil', 'telefone', 'regiao', 'cidade', 'foto', 'is_active',
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'perfil': forms.Select(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input'}),
            'regiao': forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'foto': forms.FileInput(attrs={'class': 'form-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Perfil: apenas admin e operador
        self.fields['perfil'].choices = [
            ('admin', 'Administrador'),
            ('operador', 'Operador'),
        ]
        # Todos obrigatórios exceto foto, senha, seções e is_active
        for name, field in self.fields.items():
            if name not in ('foto', 'password', 'secoes', 'areas', 'is_active'):
                field.required = True
                if hasattr(field.widget, 'attrs'):
                    field.widget.attrs['required'] = 'required'
        self.fields['regiao'].queryset = Regiao.objects.all().order_by('sigla')
        self.fields['regiao'].empty_label = '---------'
        if self.instance.pk and self.instance.regiao_id:
            self.fields['cidade'].queryset = Cidade.objects.filter(regiao=self.instance.regiao).order_by('nome')
        else:
            regiao_id = self.data.get('regiao') if self.data else None
            if regiao_id:
                try:
                    self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=int(regiao_id)).order_by('nome')
                except (ValueError, TypeError):
                    self.fields['cidade'].queryset = Cidade.objects.none()
            else:
                self.fields['cidade'].queryset = Cidade.objects.none()
        if self.instance.pk:
            self.fields['secoes'].initial = self.instance.secoes_permitidas
            self.fields['areas'].initial = self.instance.areas_tarefas
        self.aplicar_cidade_primeiro()

    def clean(self):
        cleaned = super().clean()
        return self.derivar_regiao(cleaned)

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        user.secoes_permitidas = self.cleaned_data.get('secoes', [])
        user.areas_tarefas = self.cleaned_data.get('areas', [])
        if commit:
            user.save()
        return user


class UsuarioPWACreateForm(CidadePrimeiroFormMixin, forms.ModelForm):
    password1 = forms.CharField(label='Senha', widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    password2 = forms.CharField(label='Confirmar senha', widget=forms.PasswordInput(attrs={'class': 'form-input'}))

    class Meta:
        model = Usuario
        fields = ['username', 'first_name', 'last_name', 'vinculo', 'regiao', 'telefone', 'instagram', 'cidade']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Sobrenome'}),
            'vinculo': forms.Select(attrs={'class': 'form-input'}),
            'regiao': forms.Select(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input'}),
            'instagram': forms.TextInput(attrs={'class': 'form-input'}),
            'cidade': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['regiao'].queryset = Regiao.objects.all().order_by('sigla')
        self.fields['regiao'].empty_label = '---------'
        self.fields['cidade'].queryset = Cidade.objects.none()
        if args and args[0]:
            regiao_id = args[0].get('regiao')
            if regiao_id:
                try:
                    self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=regiao_id).order_by('nome')
                except (ValueError, TypeError):
                    pass
        self.aplicar_cidade_primeiro()

    def clean(self):
        cleaned = super().clean()
        return self.derivar_regiao(cleaned)

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('As senhas não coincidem.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.perfil = 'operador'
        # Preserva o acesso mínimo do operador do app (antes vinha do auto-fill do save).
        if not user.secoes_permitidas:
            user.secoes_permitidas = user.get_secoes_padrao()
        if commit:
            user.save()
        return user


class UsuarioPWAEditForm(CidadePrimeiroFormMixin, forms.ModelForm):
    password = forms.CharField(
        label='Nova senha (deixe em branco para manter)',
        widget=forms.PasswordInput(attrs={'class': 'form-input'}),
        required=False,
    )

    class Meta:
        model = Usuario
        fields = ['username', 'first_name', 'last_name', 'vinculo', 'regiao', 'telefone', 'instagram', 'cidade', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'vinculo': forms.Select(attrs={'class': 'form-input'}),
            'regiao': forms.Select(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input'}),
            'instagram': forms.TextInput(attrs={'class': 'form-input'}),
            'cidade': forms.Select(attrs={'class': 'form-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['regiao'].queryset = Regiao.objects.all().order_by('sigla')
        self.fields['regiao'].empty_label = '---------'
        if self.instance.pk and self.instance.regiao_id:
            self.fields['cidade'].queryset = Cidade.objects.filter(regiao=self.instance.regiao).order_by('nome')
        else:
            self.fields['cidade'].queryset = Cidade.objects.none()
        if args and args[0]:
            regiao_id = args[0].get('regiao')
            if regiao_id:
                try:
                    self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=regiao_id).order_by('nome')
                except (ValueError, TypeError):
                    pass
        self.aplicar_cidade_primeiro()

    def clean(self):
        cleaned = super().clean()
        return self.derivar_regiao(cleaned)

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
