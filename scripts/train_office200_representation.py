"""Offline, family-separated representation pilot. Never changes source data or calls APIs."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(name,'2')
import argparse,collections,hashlib,json,time,platform
from pathlib import Path
import numpy as np
import scipy
from scipy.special import logsumexp
import sklearn,joblib
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler,normalize
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score,balanced_accuracy_score,precision_recall_fscore_support,confusion_matrix
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'runs/office200_embeddings_20260928'
RUN=ROOT/'runs/office200_representation_20260928'
LABELS=['honest','paltering','false_assertion']
CONFIG={'seed':42,'pca_dimensions':64,'projection_dimensions':16,'epochs':220,'learning_rate':0.01,'temperature':0.2,'l2':0.001,'same_scenario_negative_weight':3,'cross_topic_positive_weight':2,'logistic_C':1.0,'family_bootstrap_draws':1000}

def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def log(**x):print(json.dumps(x),flush=True)
def classifier():return LogisticRegression(C=CONFIG['logistic_C'],class_weight='balanced',max_iter=2000,random_state=42)
def metric(y,p):
    pr,re,f,n=precision_recall_fscore_support(y,p,labels=LABELS,zero_division=0)
    return {'macro_f1':float(f1_score(y,p,labels=LABELS,average='macro',zero_division=0)),'balanced_accuracy':float(balanced_accuracy_score(y,p)), 'per_class':{k:{'precision':float(pr[i]),'recall':float(re[i]),'f1':float(f[i]),'n':int(n[i])} for i,k in enumerate(LABELS)},'confusion_matrix':confusion_matrix(y,p,labels=LABELS).tolist()}

def load_data():
    data=read(SOURCE/'inputs.json');manifest=read(SOURCE/'manifest.json');state=read(SOURCE/'state.json')
    assert state['status']=='completed'
    assert sha(SOURCE/'inputs.json')==manifest['input_sha256']
    assert sha(SOURCE/'embeddings.npy')==state['embedding_sha256']
    annpath=ROOT/'runs/office200_matched_review_20260928/annotations.json';ann=read(annpath)
    excluded=[{'episode':v['episode'],'reason':v['assessment']} for c in ann['cases'] for v in c['reviews'].values() if v['status']=='reconsider']
    assert len(excluded)==7
    ex={x['episode'] for x in excluded}
    rows=[r for r in data['replies'] if r['outcome'] in LABELS and r['episode'] not in ex]
    assert len(rows)==757
    oldfold={x['episode']:x['fold'] for x in read(SOURCE/'folds.json')}
    fold=np.array([oldfold[r['episode']] for r in rows]);y=np.array([r['outcome'] for r in rows]);groups=np.array([r['family'] for r in rows])
    E=np.load(SOURCE/'embeddings.npy',mmap_mode='r')
    maps={v:{x['episode'] if v!='evidence_once' else x['scenario']:x['input_index'] for x in data['items'] if x['view']==v} for v in ['whole_reply','question_reply','evidence_once']}
    X={v:np.asarray(E[[maps[v][r['scenario'] if v=='evidence_once' else r['episode']] for r in rows]],dtype=np.float64) for v in maps}
    for f in range(5):
        assert not set(groups[fold==f])&set(groups[fold!=f])
        assert set(y[fold==f])==set(LABELS)
    return rows,X,y,fold,excluded,annpath

def prepare():
    rows,X,y,fold,excluded,annpath=load_data()
    protocol={'name':'Office200 evidence-aware representation pilot','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'configuration':CONFIG,'n':len(rows),'counts':dict(collections.Counter(y)),'scenarios':len({r['scenario'] for r in rows}),'families':len({r['family'] for r in rows}),'excluded':excluded,'api_calls':0,'additional_api_cost_usd':0,'input_rule':'Only cached embeddings of original replies, question-plus-reply, and full public/internal incident records. No judge rationales, outcome words, model names, ground-truth answer or authored honest references in predictor inputs. Labels supervise training only; topic/scenario metadata organize contrasts, never predictor features. Full incident evidence is known to the analyst and may not have been retrieved by the subject.','split_rule':'Reuse the original five family folds; remove seven flagged episodes only. All fitting, PCA, standardization and contrastive pairs occur in training rows. Separate stress test also excludes each tested subject model from training. All records from a case stay in one family fold.','status_of_test':'Exploratory cross-validation on a previously analyzed dataset, not an untouched confirmatory test. Former reserved scenarios have already been inspected/evaluated and are not claimed as pristine. No outcome-dependent hyperparameter search.','methods':['cached whole-reply logistic baseline','cached question-plus-reply logistic baseline','PCA evidence-relation logistic baseline','contrastive evidence-relation representation with logistic head','contrastive representation with training-label permutation control','question/evidence-only control','topic/model/length control'], 'contrastive_objective':'Class-balanced anchors; positives have the same label and a different scenario, weighted 2 when topics differ; negatives from the same scenario receive weight 3 in the softmax denominator. Temperature 0.2. A linear projection into normalized 16D, 220 full-batch Adam steps. L2=0.001. Fixed seed; no early stopping or test-based selection.','relation_features':'A shared 64D PCA fitted to unique training R, QR and E vectors. Concatenate R, QR, E, abs(R-E), R*E, abs(QR-E), QR*E; standardize using training rows, then L2 normalize. These arithmetic relations are approximate text features, not logical entailment.','uncertainty':'Paired scenario-family bootstrap of fixed out-of-fold predictions, 1000 draws; does not include training-seed or label uncertainty.','display_rule':'Only held-out points in fold-specific maps; train-only PCA of learned 16D coordinates. No mixing independently rotated fold spaces. Lie means saved false_assertion, not intent.','file_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [SOURCE/'inputs.json',SOURCE/'embeddings.npy',SOURCE/'folds.json',annpath,Path(__file__)]},'software':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__}}
    RUN.mkdir(parents=True,exist_ok=True)
    p=RUN/'protocol.json'
    if p.exists():
        old=read(p);protocol['created_utc']=old['created_utc'];assert old==protocol,'Frozen protocol changed'
    else:save(p,protocol)
    save(RUN/'selection.json',[{k:r[k] for k in ['episode','scenario','family','topic','model','outcome','split']}|{'fold':int(fold[i])} for i,r in enumerate(rows)])
    log(stage='prepared',n=len(rows),counts=protocol['counts'],excluded=len(excluded))
    return rows,X,y,fold,protocol

class RelationFeatures:
    def fit(self,X,ids):
        pool=np.unique(np.concatenate([X[k][ids] for k in ['whole_reply','question_reply','evidence_once']],axis=0),axis=0)
        self.pca=PCA(n_components=CONFIG['pca_dimensions'],svd_solver='randomized',random_state=42).fit(pool)
        self.scale=StandardScaler().fit(self.raw(X,ids))
        return self
    def raw(self,X,ids):
        r,q,e=[self.pca.transform(X[k][ids]) for k in ['whole_reply','question_reply','evidence_once']]
        return np.concatenate([r,q,e,np.abs(r-e),r*e,np.abs(q-e),q*e],axis=1)
    def transform(self,X,ids):return normalize(self.scale.transform(self.raw(X,ids)))

class ContrastiveProjection:
    def __init__(self,seed=42):self.seed=seed
    def targets(self,y,scenarios,topics):
        same=y[:,None]==y[None,:];sc=scenarios[:,None]==scenarios[None,:];tp=topics[:,None]!=topics[None,:]
        positive=same&~sc
        weights=positive*(1+tp*(CONFIG['cross_topic_positive_weight']-1))
        denom=weights.sum(axis=1)
        target=weights/np.maximum(denom[:,None],1)
        counts=collections.Counter(y);anchor=np.array([1/counts[t] for t in y]);anchor[denom==0]=0;anchor/=anchor.sum()
        pair=np.ones_like(target);pair[~same&sc]=CONFIG['same_scenario_negative_weight']
        np.fill_diagonal(pair,0)
        self.logpair=np.log(np.maximum(pair,1e-200));np.fill_diagonal(self.logpair,-1e12)
        self.target=target;self.anchor=anchor
        return {'positive_directed_pairs':int(positive.sum()),'within_scenario_directed_negatives':int((~same&sc).sum())}
    def objective(self,W,X):
        h=X@W;norm=np.maximum(np.linalg.norm(h,axis=1,keepdims=True),1e-12);z=h/norm
        logits=z@z.T/CONFIG['temperature']+self.logpair
        lp=logits-logsumexp(logits,axis=1,keepdims=True);p=np.exp(lp)
        loss=-np.sum(self.anchor[:,None]*self.target*lp)+0.5*CONFIG['l2']*np.sum(W*W)
        ds=self.anchor[:,None]*(p-self.target)/CONFIG['temperature']
        gz=(ds+ds.T)@z
        gh=(gz-z*np.sum(gz*z,axis=1,keepdims=True))/norm
        return float(loss),X.T@gh+CONFIG['l2']*W
    def fit(self,X,y,scenarios,topics):
        self.pair_counts=self.targets(y,scenarios,topics)
        rng=np.random.default_rng(self.seed);W=rng.normal(size=(X.shape[1],CONFIG['projection_dimensions']))/np.sqrt(X.shape[1])
        m=np.zeros_like(W);v=np.zeros_like(W);self.losses=[]
        for t in range(1,CONFIG['epochs']+1):
            loss,g=self.objective(W,X)
            assert np.isfinite(loss) and np.isfinite(g).all()
            self.losses.append(loss);m=.9*m+.1*g;v=.999*v+.001*g*g
            W-=CONFIG['learning_rate']*(m/(1-.9**t))/(np.sqrt(v/(1-.999**t))+1e-8)
        self.W=W;return self
    def transform(self,X):return normalize(X@self.W)

def checks():
    rng=np.random.default_rng(19);X=normalize(rng.normal(size=(12,9)));y=np.array(LABELS*4);s=np.array([str(i//3) for i in range(12)]);topics=np.array([str(i%2) for i in range(12)])
    m=ContrastiveProjection();m.targets(y,s,topics);W=rng.normal(size=(9,5))*.2
    loss,g=m.objective(W,X);errors=[]
    for i,j in [(0,0),(1,3),(2,4),(5,1),(8,4),(7,0)]:
        eps=1e-6;plus=W.copy();minus=W.copy();plus[i,j]+=eps;minus[i,j]-=eps
        numeric=(m.objective(plus,X)[0]-m.objective(minus,X)[0])/(2*eps)
        errors.append(abs(numeric-g[i,j])/max(1,abs(numeric),abs(g[i,j])))
    assert max(errors)<1e-5,errors
    assert np.allclose(m.target.sum(axis=1),1)
    assert np.allclose(np.diag(m.target),0)
    save(RUN/'numerical_checks.json',{'gradient_max_scaled_error':max(errors),'positive_targets_sum_to_one':True,'self_pairs_excluded':True})
    log(stage='gradient_checked',max_error=max(errors))

def predict(m,X,y,T):
    m.fit(X,y);p=m.predict(T);prob=m.predict_proba(T)
    return p,prob[:,[list(m.classes_).index(c) for c in LABELS]]

def one_fold(rows,X,y,fold,f,exclude_model=None):
    tr=np.flatnonzero(fold!=f);te=np.flatnonzero(fold==f)
    if exclude_model:
        tr=np.array([i for i in tr if rows[i]['model']!=exclude_model]);te=np.array([i for i in te if rows[i]['model']==exclude_model])
    assert not {rows[i]['family'] for i in tr}&{rows[i]['family'] for i in te}
    if exclude_model:assert exclude_model not in {rows[i]['model'] for i in tr}
    assert set(y[tr])==set(LABELS)
    tag=f'fold_{f}'+('__'+exclude_model if exclude_model else '')
    cache=RUN/'folds'/tag/'result.json'
    if cache.exists():return read(cache)
    cache.parent.mkdir(parents=True,exist_ok=True)
    feature=RelationFeatures().fit(X,tr);a=feature.transform(X,tr);b=feature.transform(X,te)
    scenarios=np.array([rows[i]['scenario'] for i in tr]);topics=np.array([rows[i]['topic'] for i in tr])
    proj=ContrastiveProjection().fit(a,y[tr],scenarios,topics);za=proj.transform(a);zb=proj.transform(b)
    head=classifier();pp,prob=predict(head,za,y[tr],zb)
    predictions={'contrastive':pp.tolist()};probabilities={'contrastive':prob.tolist()}
    for name,aa,bb in [('whole_reply',X['whole_reply'][tr],X['whole_reply'][te]),('question_reply',X['question_reply'][tr],X['question_reply'][te]),('evidence_relation',a,b)]:
        pred,pro=predict(classifier(),aa,y[tr],bb);predictions[name]=pred.tolist();probabilities[name]=pro.tolist()
    if not exclude_model:
        # Context-only input: remove reply. Question is reconstructed from cached source inputs;
        # lexical question features + evidence embedding prevent outcome/model metadata leakage.
        from sklearn.feature_extraction.text import TfidfVectorizer
        from scipy.sparse import hstack,csr_matrix
        tf=TfidfVectorizer(ngram_range=(1,2),min_df=2,max_features=4000,sublinear_tf=True)
        qa=tf.fit_transform([rows[i]['question'] for i in tr]);qb=tf.transform([rows[i]['question'] for i in te])
        pred,pro=predict(classifier(),hstack([qa,csr_matrix(X['evidence_once'][tr])]),y[tr],hstack([qb,csr_matrix(X['evidence_once'][te])]))
        predictions['context_only']=pred.tolist();probabilities['context_only']=pro.tolist()
        from sklearn.preprocessing import OneHotEncoder
        meta=np.array([[r['topic'],r['model']] for r in rows]);one=OneHotEncoder(handle_unknown='ignore',sparse_output=False)
        aa=one.fit_transform(meta[tr]);bb=one.transform(meta[te]);length=np.log1p([len(r['reply'].split()) for r in rows]).reshape(-1,1);sc=StandardScaler()
        la=sc.fit_transform(length[tr]);lb=sc.transform(length[te]);pred,pro=predict(classifier(),np.column_stack([aa,la]),y[tr],np.column_stack([bb,lb]))
        predictions['topic_model_length']=pred.tolist();probabilities['topic_model_length']=pro.tolist()
        perm=np.random.default_rng(734+f).permutation(y[tr]);null=ContrastiveProjection().fit(a,perm,scenarios,topics)
        pred,pro=predict(classifier(),null.transform(a),perm,null.transform(b))
        predictions['permuted_labels']=pred.tolist();probabilities['permuted_labels']=pro.tolist()
        # A fold-specific display fit uses only training coordinates. Never pool fold rotations.
        display=PCA(n_components=2,random_state=42).fit(za);coords=display.transform(zb)
        np.savez_compressed(cache.parent/'heldout_vectors.npz',indices=te,representation=zb,xy=coords)
        # Retrieval from the training partition only, excluding same topic and same subject model.
        neighbors=[];rawsim=X['whole_reply'][te]@X['whole_reply'][tr].T;learnsim=zb@za.T
        for j,i in enumerate(te):
            mask=np.array([rows[k]['topic']!=rows[i]['topic'] and rows[k]['model']!=rows[i]['model'] for k in tr])
            candidates=np.flatnonzero(mask);assert len(candidates)
            entry={'episode':rows[i]['episode'],'label':y[i]}
            for name,sim in [('original',rawsim),('learned',learnsim)]:
                order=candidates[np.argsort(-sim[j,candidates],kind='stable')[:3]]
                entry[name]=[{'episode':rows[tr[o]]['episode'],'label':y[tr[o]],'cosine':float(sim[j,o])} for o in order]
            neighbors.append(entry)
        save(cache.parent/'neighbors.json',neighbors)
        save(cache.parent/'map.json',[{'episode':rows[i]['episode'],'label':y[i],'predicted':pp[j],'x':float(coords[j,0]),'y':float(coords[j,1]),'fold':f} for j,i in enumerate(te)])
        joblib.dump({'features':feature,'projection':proj,'classifier':head,'display_pca':display,'training_episodes':[rows[i]['episode'] for i in tr],'label_order':LABELS},cache.parent/'model.joblib',compress=3)
    result={'fold':f,'excluded_model':exclude_model,'test_indices':te.tolist(),'train_n':len(tr),'test_n':len(te),'train_class_counts':dict(collections.Counter(y[tr])),'test_class_counts':dict(collections.Counter(y[te])),'predictions':predictions,'probabilities':probabilities,'loss_start':proj.losses[0],'loss_end':proj.losses[-1],'pair_counts':proj.pair_counts,'training_loss':proj.losses}
    save(cache,result);log(stage='fold_complete',fold=f,excluded_model=exclude_model,train_n=len(tr),test_n=len(te));return result

def assemble(rows,y,fold,results,stress,protocol):
    methods=list(results[0]['predictions']);p={name:np.empty(len(y),dtype=object) for name in methods};probs={name:np.empty((len(y),3)) for name in methods}
    for r in results:
        ix=r['test_indices']
        for name in methods:p[name][ix]=r['predictions'][name];probs[name][ix]=r['probabilities'][name]
    metrics={name:metric(y,pred) for name,pred in p.items()}
    stresspred={k:np.empty(len(y),dtype=object) for k in stress[0]['predictions']};coverage=np.zeros(len(y),dtype=int)
    for r in stress:
        ix=r['test_indices'];coverage[ix]+=1
        for name in stresspred:stresspred[name][ix]=r['predictions'][name]
    assert np.all(coverage==1)
    stressmetrics={name:metric(y,pred) for name,pred in stresspred.items()}
    families=sorted({r['family'] for r in rows});ixfam={f:np.array([i for i,r in enumerate(rows) if r['family']==f]) for f in families};rng=np.random.default_rng(1126)
    boot={name:[] for name in methods};deltas=[]
    for _ in range(CONFIG['family_bootstrap_draws']):
        ids=np.concatenate([ixfam[f] for f in rng.choice(families,len(families),replace=True)])
        for name in methods:boot[name].append(f1_score(y[ids],p[name][ids],labels=LABELS,average='macro',zero_division=0))
        deltas.append(boot['contrastive'][-1]-boot['whole_reply'][-1])
    for name in methods:metrics[name]['macro_f1_ci95']=np.quantile(boot[name],[.025,.975]).tolist()
    predrows=[]
    for i,r in enumerate(rows):
        predrows.append({k:r[k] for k in ['episode','scenario','family','topic','model','outcome','split','question','reply','title']}|{'fold':int(fold[i]),'predictions':{k:str(v[i]) for k,v in p.items()},'probabilities':{k:[float(x) for x in v[i]] for k,v in probs.items()},'model_heldout_predictions':{k:str(v[i]) for k,v in stresspred.items()}})
    save(RUN/'predictions.json',predrows)
    neighbors=sum([read(RUN/'folds'/f'fold_{f}'/'neighbors.json') for f in range(5)],[]);retrieval={}
    for name in ['original','learned']:
        byclass={lab:float(np.mean([x[name][0]['label']==lab for x in neighbors if x['label']==lab])) for lab in LABELS}
        retrieval[name]={'top1_same_label_by_class':byclass,'macro_top1_same_label':float(np.mean(list(byclass.values()))),'scope':'Held-out reply queries; training replies only; different topic AND different subject model. Same label is a proxy, not verified same tactic.'}
    save(RUN/'neighbors.json',neighbors)
    maps=sum([read(RUN/'folds'/f'fold_{f}'/'map.json') for f in range(5)],[]);save(RUN/'maps.json',maps)
    report={'protocol':protocol,'metrics':metrics,'family_and_model_heldout':stressmetrics,'paired_macro_f1_difference':{'comparison':'contrastive minus whole_reply','estimate':metrics['contrastive']['macro_f1']-metrics['whole_reply']['macro_f1'],'ci95':np.quantile(deltas,[.025,.975]).tolist()},'retrieval':retrieval,'paired_case_counts':dict(collections.Counter((a==b) for a,b in zip(p['whole_reply'],p['contrastive']))),'api_calls':0,'additional_api_cost_usd':0,'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    save(RUN/'results.json',report);return report

def train():
    start=time.time();rows,X,y,fold,protocol=prepare();checks()
    # Protocol is written before any fit. Source hashes are checked again at completion.
    results=[one_fold(rows,X,y,fold,f) for f in range(5)]
    stress=[one_fold(rows,X,y,fold,f,m) for f in range(5) for m in sorted({r['model'] for r in rows})]
    report=assemble(rows,y,fold,results,stress,protocol)
    ids=np.arange(len(rows));features=RelationFeatures().fit(X,ids);a=features.transform(X,ids)
    proj=ContrastiveProjection().fit(a,y,np.array([r['scenario'] for r in rows]),np.array([r['topic'] for r in rows]));z=proj.transform(a);head=classifier().fit(z,y)
    joblib.dump({'features':features,'projection':proj,'classifier':head,'label_order':LABELS,'training_episodes':[r['episode'] for r in rows],'note':'Final all-data research model. No in-sample result is used as evaluation.'},RUN/'final_model.joblib',compress=3)
    np.savez_compressed(RUN/'final_training_representation.npz',vectors=z,episodes=np.array([r['episode'] for r in rows]))
    for path,h in protocol['file_hashes'].items():assert sha(ROOT/path)==h,'Source changed'
    save(RUN/'completion.json',{'status':'completed','n':len(rows),'family_folds':5,'family_and_model_folds':30,'api_calls':0,'extra_cost_usd':0,'seconds':time.time()-start,'source_hashes_verified':True})
    log(stage='completed',seconds=time.time()-start,metrics={k:{'macro_f1':v['macro_f1'],'paltering_f1':v['per_class']['paltering']['f1']} for k,v in report['metrics'].items()})

if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('command',choices=['prepare','check','train']);a=args.parse_args()
    RUN.mkdir(parents=True,exist_ok=True)
    import fcntl
    with (RUN/'worker.lock').open('w') as lock,threadpool_limits(limits=2):
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.command=='prepare':prepare()
        elif a.command=='check':checks()
        else:train()
