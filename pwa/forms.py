from django import forms
from liderancas.models import Lideranca, Cidade, Regiao, Voluntario
from usuarios.models import Usuario


class ApoiadorPWAForm(forms.ModelForm):
    """Cadastro de apoiador via PWA — 5 campos: Nome, Cidade, Telefone, Categoria, Observações.
    Cidade é um select único com todas as cidades (funciona offline, sem cascata)."""
    tipo = forms.ChoiceField(
        label='Categoria',
        choices=[c for c in Lideranca.TIPO_CHOICES if c[0] != 'pwa'],
        widget=forms.RadioSelect(attrs={'class': 'pwa-radio'}),
    )

    class Meta:
        model = Lideranca
        fields = ['nome', 'cidade', 'telefone', 'tipo', 'observacoes']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'pwa-input', 'placeholder': 'Nome completo'}),
            'cidade': forms.Select(attrs={'class': 'pwa-input', 'id': 'id_cidade'}),
            'telefone': forms.TextInput(attrs={'class': 'pwa-input', 'placeholder': '(00) 00000-0000'}),
            'observacoes': forms.Textarea(attrs={'class': 'pwa-input', 'placeholder': 'Observações...', 'rows': 3}),
        }

    field_order = ['nome', 'cidade', 'telefone', 'tipo', 'observacoes']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['cidade'].queryset = Cidade.objects.select_related('regiao').order_by('nome')
        self.fields['cidade'].empty_label = 'Selecione a cidade…'

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.papel = 'apoiador'
        cidade = self.cleaned_data.get('cidade')
        instance.regiao = cidade.regiao if cidade else None
        if commit:
            instance.save()
        return instance


class ReplicadorForm(forms.Form):
    nome = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'pwa-input', 'placeholder': 'Nome completo'}),
    )
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all().order_by('sigla'),
        label='Região',
        widget=forms.Select(attrs={'class': 'pwa-input', 'id': 'id_regiao'}),
    )
    cidade = forms.ModelChoiceField(
        queryset=Cidade.objects.none(),
        label='Cidade',
        widget=forms.Select(attrs={'class': 'pwa-input', 'id': 'id_cidade'}),
    )
    telefone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'pwa-input', 'placeholder': '(00) 00000-0000'}),
    )
    instagram = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'pwa-input pwa-input-at', 'placeholder': 'usuario'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        data = args[0] if args else None
        if data and data.get('regiao'):
            try:
                regiao_id = int(data.get('regiao'))
                self.fields['cidade'].queryset = Cidade.objects.filter(
                    regiao_id=regiao_id
                ).order_by('nome')
            except (ValueError, TypeError):
                self.fields['cidade'].queryset = Cidade.objects.none()
        else:
            self.fields['cidade'].queryset = Cidade.objects.none()

    def save(self, convidado_por):
        dados = self.cleaned_data
        nome_parts = dados['nome'].strip().split(' ', 1)
        first_name = nome_parts[0]
        last_name = nome_parts[1] if len(nome_parts) > 1 else ''

        # Gerar username único a partir do telefone ou nome
        telefone = dados.get('telefone', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if telefone:
            username = telefone
            n = 1
            while Usuario.objects.filter(username=username).exists():
                username = f'{telefone}_{n}'
                n += 1
        else:
            base = dados['nome'].lower().replace(' ', '.')
            username = base
            n = 1
            while Usuario.objects.filter(username=username).exists():
                username = f'{base}{n}'
                n += 1

        # Senha: últimos 4 dígitos do telefone + primeiro nome minúsculo
        if len(telefone) >= 4:
            senha = telefone[-4:] + first_name.lower()
        else:
            senha = first_name.lower() + '2026'

        user = Usuario.objects.create_user(
            username=username,
            password=senha,
            first_name=first_name,
            last_name=last_name,
            telefone=dados.get('telefone', ''),
            instagram=dados.get('instagram', ''),
            cidade=dados['cidade'],
            vinculo='replicador',
            perfil='operador',
            convidado_por=convidado_por,
        )
        return user, senha


class VoluntarioPWAForm(forms.ModelForm):
    """Cadastro de voluntário via PWA — funciona offline (cidade = select único
    com todas as cidades; região derivada da cidade no save)."""
    disponibilidades = forms.MultipleChoiceField(
        choices=Voluntario.DISPONIBILIDADE_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'pwa-check'}),
        label='Disponibilidade',
    )

    class Meta:
        model = Voluntario
        fields = ['nome', 'telefone', 'cidade', 'observacoes']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'pwa-input', 'placeholder': 'Nome completo'}),
            'telefone': forms.TextInput(attrs={'class': 'pwa-input', 'placeholder': '(00) 00000-0000'}),
            'cidade': forms.Select(attrs={'class': 'pwa-input', 'id': 'id_cidade'}),
            'observacoes': forms.Textarea(attrs={'class': 'pwa-input', 'placeholder': 'Observações...', 'rows': 3}),
        }

    field_order = ['nome', 'telefone', 'cidade', 'disponibilidades', 'observacoes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cidade'].queryset = Cidade.objects.select_related('regiao').order_by('nome')
        self.fields['cidade'].empty_label = 'Selecione a cidade…'

    def save(self, commit=True):
        instance = super().save(commit=False)
        cidade = self.cleaned_data.get('cidade')
        instance.regiao = cidade.regiao if cidade else None
        instance.disponibilidades = self.cleaned_data.get('disponibilidades', [])
        if commit:
            instance.save()
        return instance
