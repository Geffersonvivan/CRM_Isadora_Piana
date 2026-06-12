from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from liderancas.models import Cidade


@login_required
def api_cidades(request, regiao_id):
    """Cidades de uma região para selects encadeados — compartilhada por todos os apps."""
    cidades = (
        Cidade.objects.filter(regiao_id=regiao_id)
        .order_by('nome')
        .values('id', 'nome')
    )
    return JsonResponse(list(cidades), safe=False)
