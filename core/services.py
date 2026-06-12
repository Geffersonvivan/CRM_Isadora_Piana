from django.db.models import Count

from liderancas.models import Apoiador
from usuarios.models import Usuario


def calcular_scores_rede():
    """Pré-calcula cadastros diretos e convidados de todos os usuários em 2 queries.

    Retorna (diretos_map, convidados_map): apoiadores cadastrados por usuário e
    lista de ids de usuários convidados por cada usuário. A "rede" de um usuário
    é a soma dos diretos dos seus convidados.
    """
    diretos_map = dict(
        Apoiador.objects.exclude(cadastrado_por=None)
        .values('cadastrado_por')
        .annotate(total=Count('id'))
        .values_list('cadastrado_por', 'total')
    )
    convidados_map = {}
    for uid, convidado_por_id in Usuario.objects.exclude(
        convidado_por=None,
    ).values_list('id', 'convidado_por_id'):
        convidados_map.setdefault(convidado_por_id, []).append(uid)
    return diretos_map, convidados_map


def score_usuario(user_id, diretos_map, convidados_map):
    """Retorna (diretos, rede, total, convidados) de um usuário a partir dos mapas."""
    diretos = diretos_map.get(user_id, 0)
    convidados = convidados_map.get(user_id, [])
    rede = sum(diretos_map.get(cid, 0) for cid in convidados)
    return diretos, rede, diretos + rede, convidados
