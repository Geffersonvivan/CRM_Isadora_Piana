import re
from django import forms
from core.forms import CidadePrimeiroFormMixin
from usuarios.models import Usuario
from .models import Lideranca, Voluntario, Cidade, Regiao, InteracaoLog


class DuplicateCheckMixin:
    """Verifica duplicatas por telefone e email no clean."""

    def _normalize_phone(self, phone):
        return re.sub(r'\D', '', phone) if phone else ''

    def _check_duplicates(self, qs):
        """qs: queryset onde procurar duplicatas (já filtrado por papel/model)."""
        telefone = self.cleaned_data.get('telefone', '')
        email = self.cleaned_data.get('email', '')
        phone_digits = self._normalize_phone(telefone)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if phone_digits and len(phone_digits) >= 10:
            for existing in qs.values_list('telefone', 'nome'):
                if self._normalize_phone(existing[0]) == phone_digits:
                    self.add_error('telefone', f'Telefone já cadastrado para: {existing[1]}')
                    break

        if email:
            dup = qs.filter(email__iexact=email).first()
            if dup:
                self.add_error('email', f'Email já cadastrado para: {dup.nome}')


class CoordenadorRegionalForm(CidadePrimeiroFormMixin, DuplicateCheckMixin, forms.ModelForm):
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all(),
        label='Região',
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
    )

    field_order = ['nome', 'telefone', 'email', 'regiao', 'cidade', 'instagram', 'prioridade', 'frequencia_relacionamento', 'observacoes']

    class Meta:
        model = Lideranca
        fields = [
            'nome', 'telefone', 'email',
            'cidade', 'instagram',
            'prioridade', 'frequencia_relacionamento',
            'observacoes',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '(00) 00000-0000'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'instagram': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '@usuario'}),
            'prioridade': forms.Select(attrs={'class': 'form-input'}),
            'frequencia_relacionamento': forms.Select(attrs={'class': 'form-input'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cidade'].label = 'Cidade Base'
        if self.instance.pk and self.instance.cidade_id:
            self.fields['regiao'].initial = self.instance.cidade.regiao_id
            self.fields['cidade'].queryset = Cidade.objects.filter(
                regiao=self.instance.cidade.regiao
            )
        else:
            regiao_id = self.data.get('regiao') if self.data else None
            if regiao_id:
                self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=regiao_id)
            else:
                self.fields['cidade'].queryset = Cidade.objects.none()
        self.aplicar_cidade_primeiro()

    def clean(self):
        super().clean()
        self.derivar_regiao(self.cleaned_data)
        self._check_duplicates(Lideranca.objects.filter(papel='coordenador'))

        cidade = self.cleaned_data.get('cidade')
        regiao = self.cleaned_data.get('regiao')
        if cidade and regiao and cidade.regiao_id != regiao.pk:
            self.add_error('cidade', 'A cidade base selecionada não pertence à região informada.')

        return self.cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.papel = 'coordenador'
        instance.regiao = self.cleaned_data['regiao']
        if commit:
            instance.save()
        return instance


class CaboEleitoralForm(CidadePrimeiroFormMixin, DuplicateCheckMixin, forms.ModelForm):
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all(),
        label='Região',
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
    )

    field_order = ['nome', 'telefone', 'email', 'regiao', 'cidade', 'instagram', 'prioridade', 'frequencia_relacionamento', 'observacoes']

    class Meta:
        model = Lideranca
        fields = [
            'nome', 'telefone', 'email',
            'cidade', 'instagram',
            'prioridade', 'frequencia_relacionamento',
            'observacoes',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '(00) 00000-0000'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'instagram': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '@usuario'}),
            'prioridade': forms.Select(attrs={'class': 'form-input'}),
            'frequencia_relacionamento': forms.Select(attrs={'class': 'form-input'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.cidade_id:
            self.fields['regiao'].initial = self.instance.cidade.regiao_id
            self.fields['cidade'].queryset = Cidade.objects.filter(
                regiao=self.instance.cidade.regiao
            )
        else:
            regiao_id = self.data.get('regiao') if self.data else None
            if regiao_id:
                self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=regiao_id)
            else:
                self.fields['cidade'].queryset = Cidade.objects.none()
        self.aplicar_cidade_primeiro()

    def clean(self):
        super().clean()
        self.derivar_regiao(self.cleaned_data)
        self._check_duplicates(Lideranca.objects.filter(papel='cabo'))

        cidade = self.cleaned_data.get('cidade')
        regiao = self.cleaned_data.get('regiao')
        if cidade and regiao and cidade.regiao_id != regiao.pk:
            self.add_error('cidade', 'A cidade selecionada não pertence à região informada.')

        return self.cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.papel = 'cabo'
        cidade = self.cleaned_data['cidade']
        instance.regiao = cidade.regiao if cidade else None
        coord = Lideranca.objects.filter(papel='coordenador', regiao=cidade.regiao).first() if cidade else None
        if coord:
            instance.coordenador_responsavel = coord
        if commit:
            instance.save()
        return instance


class ApoiadorForm(CidadePrimeiroFormMixin, DuplicateCheckMixin, forms.ModelForm):
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all(),
        label='Região',
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
    )
    # Categoria múltipla (o apoiador pode ter mais de uma). `tipo` (principal)
    # é derivado da lista no save() do model — não vai mais no ModelForm.
    tipos = forms.MultipleChoiceField(
        label='Categoria',
        required=False,
        choices=[c for c in Lideranca.TIPO_CHOICES if c[0] != 'pwa'],
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check'}),
    )

    field_order = [
        'nome', 'telefone', 'email', 'regiao', 'cidade', 'uf',
        'tipos', 'cargo', 'nivel', 'votos_referencia', 'meta_votos_transferir',
        'origem_contato', 'instagram', 'facebook',
        'prioridade', 'grau_influencia', 'frequencia_relacionamento', 'status',
        # PLANILHA CENTRAL — atendimento & relacionamento
        'atendente', 'contato_feito', 'data_contato', 'canal_atendimento',
        'intencao_voto', 'quem_e_eleitor', 'filiado_partido', 'segmentos', 'idade',
        'vaquinha_enviada', 'doou', 'material_entregue', 'endereco',
        'observacoes',
    ]

    class Meta:
        model = Lideranca
        fields = [
            'nome', 'telefone', 'email', 'cidade', 'uf',
            'cargo', 'nivel', 'votos_referencia', 'meta_votos_transferir',
            'origem_contato', 'instagram', 'facebook',
            'prioridade', 'grau_influencia',
            'frequencia_relacionamento',
            'status',
            # PLANILHA CENTRAL ISA
            'atendente', 'atendente_user', 'contato_feito', 'data_contato', 'canal_atendimento',
            'intencao_voto', 'quem_e_eleitor', 'filiado_partido', 'segmentos', 'idade',
            'vaquinha_enviada', 'doou', 'material_entregue', 'endereco',
            'observacoes',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '(00) 00000-0000'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'uf': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'SC', 'maxlength': 2}),
            'cargo': forms.Select(attrs={'class': 'form-input'}),
            'nivel': forms.Select(attrs={'class': 'form-input'}),
            'votos_referencia': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '0'}),
            'meta_votos_transferir': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '0'}),
            'origem_contato': forms.TextInput(attrs={'class': 'form-input'}),
            'instagram': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '@usuario'}),
            'facebook': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'usuário ou link'}),
            'prioridade': forms.Select(attrs={'class': 'form-input'}),
            'grau_influencia': forms.Select(attrs={'class': 'form-input'}),
            'frequencia_relacionamento': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            # PLANILHA CENTRAL
            'atendente': forms.TextInput(attrs={'class': 'form-input'}),
            'atendente_user': forms.Select(attrs={'class': 'form-input'}),
            'data_contato': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'canal_atendimento': forms.Select(attrs={'class': 'form-input'}),
            'intencao_voto': forms.Select(attrs={'class': 'form-input'}),
            'quem_e_eleitor': forms.TextInput(attrs={'class': 'form-input'}),
            'filiado_partido': forms.TextInput(attrs={'class': 'form-input'}),
            'segmentos': forms.TextInput(attrs={'class': 'form-input'}),
            'idade': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '—', 'min': 0}),
            'endereco': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Rua, nº, bairro...'}),
            'contato_feito': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'vaquinha_enviada': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'doou': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'material_entregue': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        from django.conf import settings
        isadora_layout = settings.CAMPANHA.get('LIDERANCA_INLINE_EDIT', False)

        if isadora_layout:
            # Form alinhado à PLANILHA CENTRAL da Isadora: Atendente puxa os usuários
            # cadastrados; some o funil de vendas (cargo, votos, prioridade, etc.).
            self.fields['atendente_user'].queryset = Usuario.objects.filter(
                is_active=True).order_by('first_name', 'username')
            self.fields['atendente_user'].required = False
            self.fields['atendente_user'].label = 'Atendente'
            # Cidade é o ponto de partida: select completo (com as 3 regiões
            # pré-carregadas para o lookup do JS derivar meso/micro/assoc).
            self.fields['cidade'].queryset = Cidade.objects.select_related(
                'regiao', 'microrregiao', 'mesorregiao').order_by('nome')
            # rótulos fiéis à planilha
            self.fields['intencao_voto'].label = 'Voto'
            self.fields['origem_contato'].label = 'Como chegou'
            for f in ('cargo', 'votos_referencia', 'meta_votos_transferir', 'prioridade',
                      'grau_influencia', 'frequencia_relacionamento', 'status',
                      'atendente', 'tipos', 'regiao'):
                self.fields.pop(f, None)
            # Território derivado da cidade (Isadora): escolhida a cidade, Meso/Micro/
            # Associação são preenchidas sozinhas (read-only). Não são gravadas na
            # liderança — a região é propriedade da cidade; o JS só as exibe.
            for nome, label in (('assoc_display', 'Associação'),
                                ('micro_display', 'Microrregião'),
                                ('meso_display', 'Mesorregião')):
                self.fields[nome] = forms.CharField(
                    label=label, required=False,
                    widget=forms.TextInput(attrs={
                        'class': 'form-input', 'id': f'id_{nome}',
                        'readonly': True, 'disabled': True, 'placeholder': '—',
                        'data-derivado': 'regiao',
                    }),
                )
            if self.instance.pk and self.instance.cidade_id:
                c = self.instance.cidade
                self.fields['assoc_display'].initial = c.regiao.sigla if c.regiao_id else ''
                self.fields['micro_display'].initial = c.microrregiao.nome if c.microrregiao_id else ''
                self.fields['meso_display'].initial = c.mesorregiao.nome if c.mesorregiao_id else ''
            # Seções do form (design em capítulos) — agrupam por como a campanha
            # pensa um apoiador: quem é, como classificamos, status de atendimento.
            self._secoes = [
                ('Contato', ['nome', 'telefone', 'email', 'cidade',
                             'assoc_display', 'micro_display', 'meso_display', 'uf',
                             'instagram', 'facebook', 'idade', 'endereco']),
                ('Classificação', ['atendente_user', 'intencao_voto', 'nivel',
                                   'quem_e_eleitor', 'origem_contato', 'filiado_partido',
                                   'segmentos']),
                ('Atendimento', ['contato_feito', 'data_contato', 'canal_atendimento',
                                 'vaquinha_enviada', 'doou', 'material_entregue']),
                ('Observações', ['observacoes']),
            ]
        else:
            # Outras marcas mantêm o form clássico — sem o seletor de usuário.
            self.fields.pop('atendente_user', None)

        if 'tipos' in self.fields and self.instance.pk:
            # Pré-seleciona as categorias já gravadas (fallback ao tipo único legado)
            self.fields['tipos'].initial = self.instance.tipos or (
                [self.instance.tipo] if self.instance.tipo else [])
        if self.instance.pk and self.instance.cidade_id and 'regiao' in self.fields:
            self.fields['regiao'].initial = self.instance.cidade.regiao_id
        # Sorgatto (cidade-primeiro): cidade completa + região derivada. No-op na
        # Isadora (layout inline já é cidade-primeiro por conta própria).
        self.aplicar_cidade_primeiro()

    def get_secoes(self):
        """Campos agrupados em seções (layout Isadora). None nas outras marcas —
        aí o template cai no loop simples."""
        secoes = getattr(self, '_secoes', None)
        if not secoes:
            return None
        out = []
        for titulo, nomes in secoes:
            campos = [self[n] for n in nomes if n in self.fields]
            if campos:
                out.append({'titulo': titulo, 'campos': campos})
        return out

        if user:
            if hasattr(user, 'coordenacao'):
                self.fields['regiao'].queryset = Regiao.objects.filter(
                    pk=user.coordenacao.regiao_id
                )
                self.fields['regiao'].initial = user.coordenacao.regiao_id
                self.fields['cidade'].queryset = Cidade.objects.filter(
                    regiao=user.coordenacao.regiao
                )
            elif hasattr(user, 'cabo_eleitoral'):
                self.fields['regiao'].queryset = Regiao.objects.filter(
                    pk=user.cabo_eleitoral.cidade.regiao_id
                )
                self.fields['regiao'].initial = user.cabo_eleitoral.cidade.regiao_id
                self.fields['cidade'].queryset = Cidade.objects.filter(
                    pk=user.cabo_eleitoral.cidade_id
                )
            else:
                regiao_id = self.data.get('regiao') if self.data else None
                if regiao_id:
                    self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=regiao_id)
                elif self.instance.pk and self.instance.cidade_id:
                    self.fields['cidade'].queryset = Cidade.objects.filter(
                        regiao=self.instance.cidade.regiao
                    )
                else:
                    self.fields['cidade'].queryset = Cidade.objects.none()
        else:
            self.fields['cidade'].queryset = Cidade.objects.none()

    def clean(self):
        super().clean()
        self.derivar_regiao(self.cleaned_data)
        self._check_duplicates(Lideranca.objects.filter(papel='apoiador'))

        cidade = self.cleaned_data.get('cidade')
        regiao = self.cleaned_data.get('regiao')
        if cidade and regiao and cidade.regiao_id != regiao.pk:
            self.add_error('cidade', 'A cidade selecionada não pertence à região informada.')

        return self.cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.papel = 'apoiador'
        cidade = self.cleaned_data.get('cidade')
        instance.regiao = cidade.regiao if cidade else None
        # tipo (principal) é derivado de tipos no save() do model. Só mexe se o
        # campo existir no form (no layout Isadora, Categoria foi removida — não
        # apagar as categorias já gravadas ao editar).
        if 'tipos' in self.fields:
            instance.tipos = self.cleaned_data.get('tipos') or []
        if commit:
            instance.save()
        return instance


class VoluntarioForm(CidadePrimeiroFormMixin, forms.ModelForm):
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all().order_by('sigla'),
        label='Região',
        required=False,
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
    )
    disponibilidades = forms.MultipleChoiceField(
        choices=Voluntario.DISPONIBILIDADE_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check'}),
        label='Disponibilidade',
    )

    class Meta:
        model = Voluntario
        fields = ['nome', 'telefone', 'cidade', 'endereco', 'observacoes']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '(00) 00000-0000'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'endereco': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Rua, nº, bairro...'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
        }

    field_order = ['nome', 'telefone', 'regiao', 'cidade', 'endereco', 'disponibilidades', 'observacoes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            if self.instance.regiao_id:
                self.fields['regiao'].initial = self.instance.regiao_id
            if self.instance.cidade_id:
                self.fields['cidade'].queryset = Cidade.objects.filter(
                    regiao=self.instance.cidade.regiao
                )
            if self.instance.disponibilidades:
                self.fields['disponibilidades'].initial = self.instance.disponibilidades

        regiao_id = self.data.get('regiao') if self.data else None
        if regiao_id:
            try:
                self.fields['cidade'].queryset = Cidade.objects.filter(regiao_id=int(regiao_id)).order_by('nome')
            except (ValueError, TypeError):
                self.fields['cidade'].queryset = Cidade.objects.none()
        elif not (self.instance.pk and self.instance.cidade_id):
            self.fields['cidade'].queryset = Cidade.objects.none()
        self.aplicar_cidade_primeiro()

    def clean(self):
        cleaned = super().clean()
        return self.derivar_regiao(cleaned)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.regiao = self.cleaned_data.get('regiao')
        instance.disponibilidades = self.cleaned_data['disponibilidades']
        if commit:
            instance.save()
        return instance


class InteracaoLogForm(forms.ModelForm):
    class Meta:
        model = InteracaoLog
        fields = ['tipo', 'descricao', 'data']
        widgets = {
            'descricao': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Descreva a interação...'}),
            'data': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
        }
