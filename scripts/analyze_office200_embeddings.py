"""Local exploratory analysis of cached vectors; makes no network/model calls."""
import json,hashlib,collections,re,os
from pathlib import Path
import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score,balanced_accuracy_score,confusion_matrix,precision_recall_fscore_support
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder,StandardScaler,normalize
from sklearn.pipeline import make_pipeline
from sklearn.neighbors import NearestNeighbors
from sklearn.dummy import DummyClassifier

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'runs/office200_embeddings_20260928';LABELS=['honest','paltering','false_assertion']
def save(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def clf():return LogisticRegression(C=1,class_weight='balanced',max_iter=2000,random_state=42)
def metrics(y,p):
 pr,re,fs,n=precision_recall_fscore_support(y,p,labels=LABELS,zero_division=0)
 return {'macro_f1':float(f1_score(y,p,labels=LABELS,average='macro',zero_division=0)),'balanced_accuracy':float(balanced_accuracy_score(y,p)),'confusion_matrix':confusion_matrix(y,p,labels=LABELS).tolist(),'per_class':{k:{'precision':float(pr[i]),'recall':float(re[i]),'f1':float(fs[i]),'n':int(n[i])} for i,k in enumerate(LABELS)}}

def main():
 data=json.loads((RUN/'inputs.json').read_text());manifest=json.loads((RUN/'manifest.json').read_text());state=json.loads((RUN/'state.json').read_text());assert state.get('status')=='completed','Embedding run is not complete'
 assert hashlib.sha256((RUN/'inputs.json').read_bytes()).hexdigest()==manifest['input_sha256']
 E=np.load(RUN/'embeddings.npy',mmap_mode='r');assert E.shape==(len(data['inputs']),3072) and np.isfinite(E).all();rows=data['replies'];n=len(rows);episode={r['episode']:i for i,r in enumerate(rows)}
 views={v:{x['episode']:x['input_index'] for x in data['items'] if x['view']==v} for v in ['whole_reply','question_reply']}
 X={v:np.asarray(E[[m[r['episode']] for r in rows]]) for v,m in views.items()}
 coords={};variances={}
 for name,a in X.items():
  p=PCA(n_components=2,svd_solver='randomized',random_state=42);coords[name]=p.fit_transform(a);variances[name]=p.explained_variance_ratio_.tolist()
 # Unsupervised, within-scenario centering for visualization only; never used in prediction.
 centered=X['whole_reply'].copy()
 for scenario in sorted({r['scenario'] for r in rows}):
  ids=[i for i,r in enumerate(rows) if r['scenario']==scenario];centered[ids]-=centered[ids].mean(axis=0)
 p=PCA(n_components=2,svd_solver='randomized',random_state=42);coords['within_scenario']=p.fit_transform(centered);variances['within_scenario']=p.explained_variance_ratio_.tolist()
 subset=np.array([i for i,r in enumerate(rows) if r['outcome'] in LABELS]);y=np.array([rows[i]['outcome'] for i in subset]);groups=np.array([rows[i]['family'] for i in subset]);models=np.array([rows[i]['model'] for i in subset]);topics=np.array([rows[i]['topic'] for i in subset]);texts=np.array([rows[i]['reply'] for i in subset]);questions=np.array([rows[i]['question'] for i in subset])
 folds=list(StratifiedGroupKFold(n_splits=5,shuffle=True,random_state=42).split(subset,y,groups));fold_ids=np.zeros(len(subset),dtype=int)
 for f,(tr,te) in enumerate(folds):assert not set(groups[tr])&set(groups[te]);fold_ids[te]=f
 save(RUN/'folds.json',[{'episode':rows[i]['episode'],'family':rows[i]['family'],'fold':int(fold_ids[j])} for j,i in enumerate(subset)])
 results={};predictions={}
 names=['whole_reply','question_reply','word_tfidf','question_only_tfidf','topic_model_length','majority','shuffled_labels']
 for name in names:
  pred=np.empty(len(y),dtype=object)
  for tr,te in folds:
   if name in X or name=='shuffled_labels':
    a=X['whole_reply' if name=='shuffled_labels' else name][subset];model=clf();target=y[tr].copy()
    if name=='shuffled_labels':np.random.default_rng(42+int(fold_ids[te[0]])).shuffle(target)
    model.fit(a[tr],target);pred[te]=model.predict(a[te])
   elif name in ('word_tfidf','question_only_tfidf'):
    a=texts if name=='word_tfidf' else questions
    model=make_pipeline(TfidfVectorizer(ngram_range=(1,2),min_df=2,max_features=12000,sublinear_tf=True),clf());model.fit(a[tr],y[tr]);pred[te]=model.predict(a[te])
   elif name=='topic_model_length':
    # This baseline deliberately uses metadata to test confounding, not encoder inputs.
    a=np.column_stack([topics,models]);one=OneHotEncoder(handle_unknown='ignore',sparse_output=False);at=one.fit_transform(a[tr]);ae=one.transform(a[te]);length=np.log1p([len(t.split()) for t in texts]).reshape(-1,1);scale=StandardScaler();lt=scale.fit_transform(length[tr]);le=scale.transform(length[te]);model=clf();model.fit(np.column_stack([at,lt]),y[tr]);pred[te]=model.predict(np.column_stack([ae,le]))
   else:model=DummyClassifier(strategy='most_frequent');model.fit(np.zeros((len(tr),1)),y[tr]);pred[te]=model.predict(np.zeros((len(te),1)))
  results[name]=metrics(y,pred);predictions[name]=pred;print(json.dumps({'finished_analysis':name,**results[name]}),flush=True)
 # Hold out both the subject model and the scenario family, using the fixed family folds.
 cross=np.empty(len(y),dtype=object)
 for tr,te in folds:
  for model_id in sorted(set(models)):
   a=tr[models[tr]!=model_id];b=te[models[te]==model_id]
   if not len(b):continue
   assert set(y[a])==set(LABELS);m=clf();m.fit(X['whole_reply'][subset[a]],y[a]);cross[b]=m.predict(X['whole_reply'][subset[b]])
 results['family_and_model_held_out']=metrics(y,cross);predictions['family_and_model_held_out']=cross
 # Cluster bootstrap on fixed out-of-fold predictions, not retraining; descriptive uncertainty.
 families=sorted(set(groups));rng=np.random.default_rng(123);boot={k:[] for k in results}
 for _ in range(300):
  picked=rng.choice(families,len(families),replace=True);ix=np.concatenate([np.flatnonzero(groups==g) for g in picked])
  for key,pred in predictions.items():boot[key].append(f1_score(y[ix],pred[ix],labels=LABELS,average='macro',zero_division=0))
 for key in results:results[key]['macro_f1_family_bootstrap_95']=np.quantile(boot[key],[.025,.975]).tolist()
 save(RUN/'predictions.json',[{'episode':rows[i]['episode'],'saved_label':y[j],**{k:str(v[j]) for k,v in predictions.items()}} for j,i in enumerate(subset)])
 # Distances in full 3072D space. Nearest same-topic neighbors reveal topic dependence.
 sims=X['whole_reply']@X['whole_reply'].T;np.fill_diagonal(sims,-np.inf)
 nearest=[];same_topic=0;same_model=0
 for i,r in enumerate(rows):
  scores=sims[i].copy();scores[[j for j,x in enumerate(rows) if x['scenario']==r['scenario']]]=-np.inf
  j=int(scores.argmax());same_topic+=rows[j]['topic']==r['topic'];same_model+=rows[j]['model']==r['model']
  scores[[j for j,x in enumerate(rows) if x['topic']==r['topic']]]=-np.inf
  ids=np.argsort(scores)[-3:][::-1];nearest.append([{'episode':rows[j]['episode'],'cosine':round(float(scores[j]),4)} for j in ids])
 # Contextual sentence-unit neighbors across topics. Exclude short boilerplate from this view only.
 units=[x for x in data['items'] if x['view']=='question_unit' and len(x['text'].split())>=8 and not re.search(r'^(dear\b|sincerely\b|thank you\b|best regards\b|constituent services\b|this response was prepared\b)',x['text'],re.I)]
 a=np.asarray(E[[x['input_index'] for x in units]]);nn=NearestNeighbors(metric='cosine',algorithm='brute',n_jobs=1).fit(a)
 candidates=[]
 query_indices=[i for i,u in enumerate(units) if rows[episode[u['episode']]]['outcome']=='paltering']
 for start in range(0,len(query_indices),128):
  batch=query_indices[start:start+128]
  dist,inds=nn.kneighbors(a[batch],n_neighbors=min(100,len(units)))
  for off,(ds,js) in enumerate(zip(dist,inds)):
   i=batch[off];u=units[i];r=rows[episode[u['episode']]]
   for dd,j in zip(ds,js):
    other=units[j];v=rows[episode[other['episode']]]
    if v['topic']!=r['topic'] and other['text']!=u['text']:
     candidates.append({'a':{'episode':u['episode'],'unit':u['unit_id'],'text':u['text']},'b':{'episode':other['episode'],'unit':other['unit_id'],'text':other['text']},'cosine':round(float(1-dd),4)});break
  if start%1024==0:print(json.dumps({'unit_neighbors':min(start+128,len(query_indices)),'total':len(query_indices)}),flush=True)
 # Display up to 20 nonduplicate pairs touching joint paltering, selected by similarity, not handpicked.
 candidates.sort(key=lambda x:-x['cosine']);pairs=[];used=set()
 for pair in candidates:
  u,v=pair['a'],pair['b'];ra,rb=rows[episode[u['episode']]],rows[episode[v['episode']]]
  if ra['outcome']!='paltering' and rb['outcome']!='paltering':continue
  keys={(u['episode'],u['unit']),(v['episode'],v['unit'])}
  if keys&used:continue
  pairs.append(pair);used|=keys
  if len(pairs)==20:break
 # Existing editorial tactic labels are display metadata only, never encoder/classifier targets here.
 annotations=json.loads((ROOT.parent/'paltering-research-site/mechanism_annotations.json').read_text())['assignments']
 outrows=[]
 for i,r in enumerate(rows):outrows.append({**r,'tactic':annotations.get(r['episode']),'coordinates':{k:[round(float(z),6) for z in c[i]] for k,c in coords.items()},'cross_topic_neighbors':nearest[i]})
 report={'encoder':manifest['model'],'dimensions':3072,'n_replies':n,'n_label_comparison':len(subset),'outcomes':dict(collections.Counter(r['outcome'] for r in rows)),'pca_variance_ratio':variances,'metrics':results,'label_order':LABELS,'family_count':len(families),'evaluation':'Fixed balanced logistic regression C=1; five stratified scenario-family folds, seed 42. Final row holds out both subject model and scenario family. Outcome targets are existing automated judge agreement, not independent human truth. Confidence intervals resample families of fixed out-of-fold predictions; they are not test-retest intervals. One fixed shuffled-label control, not a significance test.','nearest_neighbor_diagnostics':{'scope':'Nearest other-scenario whole reply, full 3072D cosine','same_topic_fraction':same_topic/n,'same_model_fraction':same_model/n},'unit_neighbors':{'eligible_units':len(units),'query_units_from_joint_paltering':len(query_indices),'searched_neighbors':100,'cross_topic_pairs_found':len(candidates),'display_pairs':len(pairs),'scope':'Question + sentence embeddings; queries come from jointly labeled paltering replies, searched against all eligible units; top 100 neighbors screened for different topic. Display top 20 distinct pairs touching joint paltering, excluding short/greeting/signature units. Whole-reply labels are not sentence-level labels.'},'spending':state,'manifest':manifest,'rows':outrows,'unit_pairs':pairs}
 save(RUN/'analysis.json',report)
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 colors={'honest':'#397866','paltering':'#a67615','false_assertion':'#7561a6'};fig,axes=plt.subplots(1,2,figsize=(12,5.4))
 for ax,key,title in zip(axes,['whole_reply','within_scenario'],['Whole replies','After subtracting each scenario’s mean']):
  for outcome in ['other']+LABELS:
   ids=[i for i,r in enumerate(rows) if (r['outcome']==outcome if outcome!='other' else r['outcome'] not in LABELS)];xy=coords[key][ids];ax.scatter(xy[:,0],xy[:,1],s=14,alpha=.55,c=colors.get(outcome,'#b7b7b2'),label=outcome.replace('_',' '),rasterized=True)
  ax.set(title=title,xlabel=f'PC1 ({variances[key][0]:.1%} variance)',ylabel=f'PC2 ({variances[key][1]:.1%} variance)');ax.spines[['top','right']].set_visible(False)
 axes[0].legend(fontsize=8,frameon=False);fig.suptitle('Reply embeddings · saved judge labels',fontsize=14);fig.text(.5,.015,'PCA is an exploratory projection, not a measured direction of deception or recipient belief.',ha='center',fontsize=9);fig.tight_layout(rect=[0,.04,1,.94]);fig.savefig(RUN/'embedding_map.png',dpi=180);fig.savefig(RUN/'embedding_map.svg');plt.close(fig)
 print(json.dumps({'analysis_complete':True,'metrics':{k:round(v['macro_f1'],3) for k,v in results.items()},'pca_variance':variances,'neighbors':report['nearest_neighbor_diagnostics']}),flush=True)

if __name__=='__main__':main()
