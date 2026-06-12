import json
from datetime import datetime, date, time

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
from liderancas.models import Cidade
from liderancas.models import Regiao, CoordenadorRegional, CaboEleitoral, Apoiador
from .models import Compromisso, Evento, Roteiro, RoteiroPonto


class CompromissoForm(forms.ModelForm):
    # Participantes vinculados ao CRM — a UI são checkboxes no painel de
    # contatos do modal (populado via API por região/cidade); os campos aqui
    # só validam e salvam os IDs postados.
    coordenadores = forms.ModelMultipleChoiceField(
        queryset=CoordenadorRegional.objects.all(), required=False,
        widget=forms.MultipleHiddenInput,
    )
    cabos = forms.ModelMultipleChoiceField(
        queryset=CaboEleitoral.objects.all(), required=False,
        widget=forms.MultipleHiddenInput,
    )
    apoiadores = forms.ModelMultipleChoiceField(
        queryset=Apoiador.objects.all(), required=False,
        widget=forms.MultipleHiddenInput,
    )
    data = forms.DateField(
        label='Data',
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
    )
    hora_inicio = forms.TimeField(
        label='Início',
        widget=forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
        input_formats=['%H:%M'],
    )
    hora_fim = forms.TimeField(
        label='Fim',
        widget=forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
        input_formats=['%H:%M'],
    )

    class Meta:
        model = Compromisso
        fields = [
            'titulo', 'descricao',
            'tipo', 'regiao', 'cidade', 'endereco',
            'contato_local_nome', 'contato_local_telefone',
            'participantes', 'coordenadores', 'cabos', 'apoiadores',
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
        if self.instance.pk and self.instance.cidade_id:
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


class EventoForm(forms.ModelForm):
    regiao = forms.ModelChoiceField(
        queryset=Regiao.objects.all().order_by('sigla'),
        label='Região',
        required=False,
        widget=forms.Select(attrs={'class': 'form-input', 'id': 'id_regiao'}),
    )

    class Meta:
        model = Evento
        fields = [
            'nome', 'tipo', 'data', 'horario_inicio', 'horario_fim',
            'cidade', 'local', 'publico_estimado',
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
