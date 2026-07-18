import json
from datetime import datetime, date, time

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
from core.forms import CidadePrimeiroFormMixin
from liderancas.models import Cidade
from liderancas.models import Regiao, Lideranca
from .models import Compromisso, Evento, EventoAnexo, Roteiro, RoteiroPonto

ANEXO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB por arquivo


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Campo de upload que aceita vários arquivos (<input multiple>)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            'widget',
            MultipleFileInput(attrs={'class': 'form-input', 'accept': 'image/*,application/pdf'}),
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data]
        return [single(data, initial)] if data else []


class CompromissoForm(forms.ModelForm):
    # Participantes vinculados ao CRM — a UI são checkboxes no painel de
    # contatos do modal (populado via API por região/cidade); os campos aqui
    # só validam e salvam os IDs postados.
    coordenadores = forms.ModelMultipleChoiceField(
        queryset=Lideranca.objects.filter(papel='coordenador'), required=False,
        widget=forms.MultipleHiddenInput,
    )
    cabos = forms.ModelMultipleChoiceField(
        queryset=Lideranca.objects.filter(papel='cabo'), required=False,
        widget=forms.MultipleHiddenInput,
    )
    apoiadores = forms.ModelMultipleChoiceField(
        queryset=Lideranca.objects.filter(papel='apoiador'), required=False,
        widget=forms.MultipleHiddenInput,
    )
    aliados = forms.ModelMultipleChoiceField(
        queryset=None, required=False, label='Aliados de chapa presentes',
        widget=forms.CheckboxSelectMultiple,
    )
    data = forms.DateField(
        label='Data',
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
    )
    # Campo estilo Google Agenda: input de texto (digitável) + dropdown de slots
    # de 15 min com filtro e duração, montado por JS (setupTimeCombo). Os formatos
    # abaixo aceitam o que o JS normaliza e variações digitadas à mão.
    hora_inicio = forms.TimeField(
        label='Início',
        widget=forms.TextInput(attrs={
            'class': 'form-input tc-input', 'autocomplete': 'off',
            'placeholder': 'hh:mm', 'inputmode': 'numeric',
        }),
        input_formats=['%H:%M', '%H:%M:%S', '%Hh%M', '%I:%M %p', '%I:%M%p'],
    )
    hora_fim = forms.TimeField(
        label='Fim',
        widget=forms.TextInput(attrs={
            'class': 'form-input tc-input', 'autocomplete': 'off',
            'placeholder': 'hh:mm', 'inputmode': 'numeric',
        }),
        input_formats=['%H:%M', '%H:%M:%S', '%Hh%M', '%I:%M %p', '%I:%M%p'],
    )

    class Meta:
        model = Compromisso
        fields = [
            'titulo', 'descricao',
            'tipo', 'regiao', 'cidade', 'endereco',
            'contato_local_nome', 'contato_local_telefone',
            'participantes', 'coordenadores', 'cabos', 'apoiadores', 'aliados',
            'prioridade', 'status', 'observacoes',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Adicionar título'}),
            'descricao': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'tipo': forms.Select(attrs={'class': 'form-input'}),
            'regiao': forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'endereco': forms.TextInput(attrs={'class': 'form-input'}),
            'contato_local_nome': forms.TextInput(attrs={'class': 'form-input'}),
            'contato_local_telefone': forms.TextInput(
                attrs={'class': 'form-input', 'placeholder': '(00) 00000-0000'},
            ),
            'participantes': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'prioridade': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from mapa.models import AliadoChapa
        self.fields['aliados'].queryset = AliadoChapa.objects.filter(ativo=True)

        # IDs já vinculados (para o JS pré-marcar os checkboxes do painel)
        if self.instance.pk:
            self.participantes_selecionados = json.dumps({
                'coordenadores': list(self.instance.coordenadores.values_list('id', flat=True)),
                'cabos': list(self.instance.cabos.values_list('id', flat=True)),
                'apoiadores': list(self.instance.apoiadores.values_list('id', flat=True)),
            })
        else:
            self.participantes_selecionados = '{"coordenadores":[],"cabos":[],"apoiadores":[]}'

        # Populate data/hora fields from instance
        if self.instance.pk and self.instance.data_hora_inicio:
            inicio = timezone.localtime(self.instance.data_hora_inicio)
            fim = timezone.localtime(self.instance.data_hora_fim)
            self.fields['data'].initial = inicio.date()
            self.fields['hora_inicio'].initial = inicio.strftime('%H:%M')
            self.fields['hora_fim'].initial = fim.strftime('%H:%M')

        # City queryset
        from django.conf import settings
        self.cidade_primeiro = settings.CAMPANHA.get('CIDADE_PRIMEIRO', False)
        if self.cidade_primeiro:
            # Fluxo cidade-primeiro: a cidade é o ponto de partida (select com as
            # 295, buscável no front) e a região deixa de ser input do usuário —
            # é derivada da cidade em clean(). O campo região vira só-leitura.
            self.fields['cidade'].queryset = Cidade.objects.select_related(
                'regiao').order_by('nome')
            self.fields['regiao'].required = False
        elif self.instance.pk and self.instance.cidade_id:
            self.fields['cidade'].queryset = Cidade.objects.filter(
                regiao=self.instance.cidade.regiao
            )
        else:
            regiao_id = (self.data.get('regiao') if self.data else None) or self.initial.get('regiao')
            if regiao_id:
                self.fields['cidade'].queryset = Cidade.objects.filter(
                    regiao_id=regiao_id
                )
            else:
                self.fields['cidade'].queryset = Cidade.objects.none()

    def clean(self):
        cleaned = super().clean()

        # Cidade-primeiro: a região é derivada da cidade (não é input do usuário).
        if getattr(self, 'cidade_primeiro', False):
            cidade = cleaned.get('cidade')
            if cidade:
                cleaned['regiao'] = cidade.regiao

        dt = cleaned.get('data')
        hi = cleaned.get('hora_inicio')
        hf = cleaned.get('hora_fim')

        if dt and hi:
            cleaned['data_hora_inicio'] = timezone.make_aware(
                datetime.combine(dt, hi)
            )
        if dt and hf:
            cleaned['data_hora_fim'] = timezone.make_aware(
                datetime.combine(dt, hf)
            )

        if hi and hf and hf <= hi:
            self.add_error('hora_fim', 'Horário fim deve ser após o início.')

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.data_hora_inicio = self.cleaned_data['data_hora_inicio']
        instance.data_hora_fim = self.cleaned_data['data_hora_fim']
        if commit:
            instance.save()
        return instance


class RoteiroForm(forms.ModelForm):
    class Meta:
        model = Roteiro
        fields = ['titulo', 'data', 'regiao', 'motorista', 'status', 'observacoes']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-input'}),
            'data': forms.DateInput(
                attrs={'class': 'form-input', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'regiao': forms.Select(attrs={'class': 'form-input'}),
            'motorista': forms.TextInput(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data'].input_formats = ['%Y-%m-%d']


class EventoForm(CidadePrimeiroFormMixin, forms.ModelForm):
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all().order_by('sigla'),
        label='Região',
        required=False,
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
    )
    # Não faz parte do model Evento: a view grava cada arquivo como EventoAnexo.
    anexos = MultipleFileField(required=False, label='Anexos (imagens e PDFs)')

    def clean_anexos(self):
        arquivos = self.cleaned_data.get('anexos') or []
        extensoes = tuple('.' + e for e in EventoAnexo.EXTENSOES)
        for f in arquivos:
            if not f.name.lower().endswith(extensoes):
                raise forms.ValidationError(
                    f'"{f.name}": tipo não permitido. Use imagens ou PDF.')
            if f.size > ANEXO_MAX_BYTES:
                raise forms.ValidationError(
                    f'"{f.name}": arquivo maior que 10 MB.')
        return arquivos

    class Meta:
        model = Evento
        fields = [
            'nome', 'tipo', 'data', 'horario_inicio', 'horario_fim',
            'cidade', 'local', 'publico_estimado', 'aliados',
            'relevancia', 'status', 'observacoes', 'resultado', 'imagem',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome do evento'}),
            'tipo': forms.Select(attrs={'class': 'form-input'}),
            'data': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
            'horario_inicio': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'horario_fim': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'cidade': forms.Select(attrs={'class': 'form-input', 'id': 'id_cidade'}),
            'local': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Local ou endereço'}),
            'publico_estimado': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 500'}),
            'relevancia': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'resultado': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'imagem': forms.ClearableFileInput(attrs={'class': 'form-input'}),
            'aliados': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from mapa.models import AliadoChapa
        self.fields['aliados'].queryset = AliadoChapa.objects.filter(ativo=True)
        self.fields['aliados'].required = False
        self.fields['data'].input_formats = ['%Y-%m-%d']
        self.fields['horario_inicio'].input_formats = ['%H:%M', '%H:%M:%S']
        self.fields['horario_fim'].input_formats = ['%H:%M', '%H:%M:%S']

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
        # Sorgatto: cidade completa + região (só filtro, não persistida no Evento).
        self.aplicar_cidade_primeiro()


RoteiroPontoFormSet = inlineformset_factory(
    Roteiro,
    RoteiroPonto,
    fields=['compromisso', 'ordem', 'observacao_ponto'],
    extra=3,
    can_delete=True,
    widgets={
        'compromisso': forms.Select(attrs={'class': 'form-input'}),
        'ordem': forms.NumberInput(attrs={'class': 'form-input', 'style': 'width:70px'}),
        'observacao_ponto': forms.TextInput(attrs={'class': 'form-input'}),
    },
)
