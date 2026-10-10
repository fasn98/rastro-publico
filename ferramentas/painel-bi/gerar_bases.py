"""Gera as bases do painel analítico (Artifact Dashboard) a partir da exportação do site.

Uso: python3 -I gerar_bases.py <pasta dados/ do gh-pages> <pasta de saída>

Lê só arquivos já publicados (branch gh-pages). Não chama a API nem o banco e não
estima nada: soma e reorganiza os números exportados em tabelas de fatos com a
dimensão UF em todas as linhas, para valer também quando o site for nacional.
Saída: f_atividade.json, f_emendas.json, f_cota.json, f_eleitos.json, coleta.json e
meta.json (data da exportação e commit do código que a gerou).
"""
import collections
import glob
import json
import os
import sys

D,O=sys.argv[1],sys.argv[2]
os.makedirs(O,exist_ok=True)
J=lambda p: json.load(open(os.path.join(D,p)))
UF={11:'RO',12:'AC',13:'AM',14:'RR',15:'PA',16:'AP',17:'TO',21:'MA',22:'PI',23:'CE',24:'RN',25:'PB',26:'PE',27:'AL',28:'SE',29:'BA',31:'MG',32:'ES',33:'RJ',35:'SP',41:'PR',42:'SC',43:'RS',50:'MS',51:'MT',52:'GO',53:'DF'}
CARGO={'deputado_federal':'Deputado(a) federal','senador':'Senador(a)','governador':'Governador(a)','deputado_estadual':'Deputado(a) estadual','prefeito':'Prefeito(a)','vereador':'Vereador(a)'}
CASA={'camara':'Câmara dos Deputados','senado':'Senado Federal'}
num=lambda s: float(s) if s not in (None,'') else 0.0
mun={}
for m in J('municipios.json'): mun[m['cod_ibge']]=(m['nome'],m.get('populacao'))
b=J('busca.json')
for it in b['itens']:
    if b['indices']['tipo'][it['tipo']] in ('municipio','distrito_federal') and it['cod_ibge']>99: mun.setdefault(it['cod_ibge'],(it['nome'],it.get('populacao')))
def expandir(c):
    out=[]
    for it in c['itens']:
        r=dict(c.get('comum',{})); r.update(it)
        for k,vals in c.get('indices',{}).items():
            if k in it and isinstance(it[k],int): r[k]=vals[it[k]]
        out.append(r)
    return out
def partido_no_ano(p,ano):
    fim=f'{ano}-12-31T23:59:59'; best=None
    for t in p['linha_do_tempo']:
        if t.get('partido') and t['inicio']<=fim and (best is None or t['inicio']>=best['inicio']): best=t
    return best['partido'] if best else p['partido']
ativ=[];emen=[];cota=[]
for f in sorted(glob.glob(f'{D}/politicos/*.json')):
    p=json.load(open(f)); pid=p['id']; base=f'{D}/politicos/{pid}'
    dim=dict(uf=p['uf'],casa=CASA[p['fonte']],cargo=CARGO[p['cargo']],parlamentar=p['nome'],situacao='Em exercício' if p['em_exercicio'] else 'Fora de exercício',partido_atual=p['partido'])
    anos=collections.defaultdict(lambda: collections.Counter())
    for c in p['cota']: anos[c['ano']]['cota_valor']+=num(c['valor_liquido']); anos[c['ano']]['cota_despesas']+=c['quantidade']
    for k in ('presencas','proposicoes','votacoes'):
        for c in p[k]: anos[c['ano']][k]+=c['quantidade']
    for c in p['votacoes']:
        pv=c.get('por_voto') or {}; anos[c['ano']]['votos_sim']+=pv.get('Sim',0); anos[c['ano']]['votos_nao']+=pv.get('Não',0)
    for fc in glob.glob(f'{base}/cota/[0-9][0-9][0-9][0-9].json'):
        c=json.load(open(fc))
        for x in c.get('por_categoria') or []:
            cota.append(dict(dim,ano=c['ano'],partido_ano=partido_no_ano(p,c['ano']),categoria=x['categoria'].rstrip('. ').capitalize(),valor=num(x['valor_liquido']),despesas=x['quantidade']))
    for fe in glob.glob(f'{base}/emendas/*.json'):
        for it in json.load(open(fe)).get('itens') or []:
            a=it['ano']; cd=it.get('cod_ibge_destino')
            emp,liq,pag=num(it['valor_empenhado']),num(it['valor_liquidado']),num(it['valor_pago'])
            anos[a]['emendas_qtd']+=1; anos[a]['emendas_empenhado']+=emp; anos[a]['emendas_liquidado']+=liq; anos[a]['emendas_pago']+=pag
            emen.append(dict(dim,ano=a,partido_ano=partido_no_ano(p,a),codigo_emenda=it['codigo_emenda'],tipo=it.get('tipo_emenda') or 'Não informado',
                funcao=it.get('funcao') or 'Não informada',subfuncao=it.get('subfuncao') or 'Não informada',
                transferencia_especial='Sim' if it.get('transferencia_especial') else 'Não',
                destino=mun.get(cd,(str(cd),None))[0] if cd else 'Sem município único',destino_uf=UF.get(cd//100000,'—') if cd else '—',
                localidade=(it.get('localidade_gasto') or '—'),populacao_destino=mun.get(cd,(None,None))[1] if cd else None,
                empenhado=emp,liquidado=liq,pago=pag,quantidade=1,url_fonte=it.get('url_fonte'),sha256=it.get('sha256')))
    for a,m in sorted(anos.items()):
        row=dict(dim,ano=a,partido_ano=partido_no_ano(p,a),comissoes_atuais=len(p.get('comissoes') or []))
        for k in ('cota_valor','cota_despesas','presencas','proposicoes','votacoes','votos_sim','votos_nao','emendas_qtd','emendas_empenhado','emendas_liquidado','emendas_pago'):
            row[k]=round(m[k],2) if isinstance(m[k],float) else m[k]
        if p['fonte']=='senado': row['cota_valor']=row['cota_despesas']=row['presencas']=None
        ativ.append(row)
for r in cota+emen:
    for k in ('valor','empenhado','liquidado','pago'):
        if k in r: r[k]=round(r[k],2)
el=[]
for f in sorted(glob.glob(f'{D}/eleitos/*.json')):
    for r in expandir(json.load(open(f))):
        cod=r.get('cod_ibge')
        el.append(dict(uf=r['uf'],eleicao=r['eleicao_ano'],cargo=CARGO.get(r['cargo'],r['cargo']),nome=r['nome'],partido=r['partido'],situacao=r['situacao'],
            abrangencia='Municipal' if cod else 'Estadual',municipio=mun.get(cod,(str(cod),None))[0] if cod else '—',populacao_municipio=mun.get(cod,(None,None))[1] if cod else None,quantidade=1))
w=lambda n,o: json.dump(o,open(f'{O}/{n}.json','w'),ensure_ascii=False,separators=(',',':'))
w('f_atividade',ativ);w('f_emendas',emen);w('f_cota',cota);w('f_eleitos',el)
m=J('manifesto.json')
w('coleta',[dict(fonte=f['nome'],ultima_atualizacao=f['ultima_atualizacao'],disponivel=f['disponivel']) for f in m['fontes']]+[dict(fonte='Exportação do site',ultima_atualizacao=m['gerado_em'],disponivel=True)])
w('meta',dict(gerado_em=m['gerado_em'],codigo=m.get('codigo'),contagens=dict(f_atividade=len(ativ),f_emendas=len(emen),f_cota=len(cota),f_eleitos=len(el))))
print(json.dumps(dict(gerado_em=m['gerado_em'],f_atividade=len(ativ),f_emendas=len(emen),f_cota=len(cota),f_eleitos=len(el)),ensure_ascii=False))
