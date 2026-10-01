"""Apply the saved local representation to cached 3072D vectors; no API calls."""
import numpy as np

def norm(x):
    return x/np.maximum(np.linalg.norm(x,axis=1,keepdims=True),1e-12)

def infer(weights_path,reply,question_reply,evidence):
    w=np.load(weights_path,allow_pickle=False)
    arrays=[np.atleast_2d(np.asarray(a,dtype=np.float64)) for a in [reply,question_reply,evidence]]
    assert len({a.shape for a in arrays})==1 and arrays[0].shape[1]==3072
    r,q,e=[(a-w['pca_mean'])@w['pca_components'].T for a in arrays]
    features=np.concatenate([r,q,e,abs(r-e),r*e,abs(q-e),q*e],axis=1)
    features=norm((features-w['feature_mean'])/w['feature_scale'])
    z=norm(features@w['projection'])
    logits=z@w['classifier_coef'].T+w['classifier_intercept']
    labels=w['classifier_classes'][logits.argmax(axis=1)]
    return z,labels,logits
