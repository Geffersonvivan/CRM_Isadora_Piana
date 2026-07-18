"""Utilitários de formulário compartilhados entre apps."""

from django.conf import settings


class CidadePrimeiroFormMixin:
    """Inverte o par região→cidade quando ``CAMPANHA['CIDADE_PRIMEIRO']`` (Sorgatto).

    No fluxo cidade-primeiro a cidade é o ponto de partida: o select recebe as
    295 cidades (buscável no front) e a região deixa de ser input do usuário —
    é derivada da cidade. Chame ``aplicar_cidade_primeiro()`` no ``__init__`` e
    ``derivar_regiao(cleaned)`` dentro de ``clean()``. Fora do Sorgatto os dois
    hooks são no-op e o form segue clássico.

    Só ajusta os campos ``cidade``/``regiao`` se eles existirem no form.
    """

    def aplicar_cidade_primeiro(self):
        from liderancas.models import Cidade
        self.cidade_primeiro = settings.CAMPANHA.get('CIDADE_PRIMEIRO', False)
        if not self.cidade_primeiro:
            return
        if 'cidade' in self.fields:
            self.fields['cidade'].queryset = (
                Cidade.objects.select_related('regiao').order_by('nome')
            )
        if 'regiao' in self.fields:
            self.fields['regiao'].required = False

    def derivar_regiao(self, cleaned):
        if getattr(self, 'cidade_primeiro', False) and 'regiao' in self.fields:
            cidade = cleaned.get('cidade')
            if cidade is not None:
                cleaned['regiao'] = cidade.regiao
        return cleaned
