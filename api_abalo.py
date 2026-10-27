from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, create_engine, func,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from sqlalchemy import text  
# ─────────────────────────────────────────────
# CONFIG   http://localhost:8080/dashboard-clinique.html          uvicorn api_abalo:app --host 0.0.0.0 --port 8026 --reload
# ─────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "secours-abalo-secret-key-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24h

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:beauty@localhost:5432/secours_abalo_db"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(
    title="Secours Abalo API",
    description="Backend complet – abonnements, interventions, RH, finances.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# MODÈLES SQLAlchemy
# ─────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    prenom = Column(String, nullable=False)
    nom = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    telephone = Column(String, nullable=True)
    quartier = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    abonnements = relationship("Abonnement", back_populates="user", cascade="all, delete-orphan")
    interventions = relationship("Intervention", back_populates="user", cascade="all, delete-orphan")


class Abonnement(Base):
    __tablename__ = "abonnements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    plan = Column(String, nullable=False)            # Solo | Duo+ | Famille+ | Entreprise
    prix_semaine = Column(Float, nullable=True)
    nb_personnes = Column(Integer, default=1)
    personnes_couvertes = Column(Text, nullable=True)
    mode_paiement = Column(String, nullable=True)
    statut = Column(String, default="en_attente")    # en_attente | actif | suspendu | annulé
    date_souscription = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    date_expiration = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="abonnements")


class Intervention(Base):
    __tablename__ = "interventions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    type_urgence = Column(String, nullable=False)
    localisation = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    statut = Column(String, default="urgence")       # urgence | enroute | transit | terminee
    ambulance_id = Column(String, nullable=True)
    eta_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="interventions")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    prenom = Column(String, nullable=False)
    nom = Column(String, nullable=False)
    email = Column(String, nullable=False)
    telephone = Column(String, nullable=True)
    objet = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    lu = Column(Boolean, default=False)
    repondu = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── RH ──────────────────────────────────────
class Employe(Base):
    __tablename__ = "employes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    prenom = Column(String, nullable=False)
    nom = Column(String, nullable=False)
    poste = Column(String, nullable=False)
    telephone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    date_embauche = Column(String, nullable=True)
    salaire_mensuel = Column(Float, nullable=True)
    heure_debut = Column(String, default="08:00")
    statut = Column(String, default="active")        # active | inactif
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    presences = relationship("Presence", back_populates="employe", cascade="all, delete-orphan")


class Presence(Base):
    __tablename__ = "presences"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    employe_id = Column(String, ForeignKey("employes.id"), nullable=False)
    date = Column(String, nullable=False)            # ISO date YYYY-MM-DD
    heure_arrivee = Column(String, nullable=True)
    statut = Column(String, default="present")       # present | absent | retard
    motif = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    employe = relationship("Employe", back_populates="presences")


# ── FINANCES ────────────────────────────────
class EntreeFinanciere(Base):
    __tablename__ = "entrees_financieres"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(String, nullable=False)
    reference = Column(String, nullable=True)
    categorie = Column(String, nullable=False)       # Abonnement | Renouvellement | Subvention | Don | Autre
    motif = Column(Text, nullable=False)
    payeur = Column(String, nullable=True)
    methode_paiement = Column(String, nullable=True)
    montant = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SortieFinanciere(Base):
    __tablename__ = "sorties_financieres"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(String, nullable=False)
    reference = Column(String, nullable=True)
    categorie = Column(String, nullable=False)       # Salaires | Carburant | Maintenance | ...
    motif = Column(Text, nullable=False)
    beneficiaire = Column(String, nullable=True)
    methode_paiement = Column(String, nullable=True)
    montant = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── MEDIA ───────────────────────────────────
class Image(Base):
    __tablename__ = "images"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    titre = Column(String, nullable=False)
    categorie = Column(String, nullable=True)
    url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    visibilite = Column(String, default="Publier sur le site")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    titre = Column(String, nullable=False)
    categorie = Column(String, nullable=True)
    url_source = Column(String, nullable=True)       # URL YouTube ou chemin fichier
    type_source = Column(String, default="youtube")  # youtube | upload
    duree = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Article(Base):
    __tablename__ = "articles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    titre = Column(String, nullable=False)
    categorie = Column(String, nullable=True)
    auteur = Column(String, nullable=True)
    resume = Column(Text, nullable=True)
    contenu = Column(Text, nullable=True)
    tags = Column(String, nullable=True)
    statut = Column(String, default="Publier maintenant")  # Publier maintenant | Brouillon
    image_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))



# ─────────────────────────────────────────────
# DÉPENDANCES
# ─────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_exception
    return user


def get_optional_user(
    token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == user_id).first()
    except JWTError:
        return None


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return current_user


# ─────────────────────────────────────────────
# TARIFS
# ─────────────────────────────────────────────
PLANS = {
    "Solo":       {"prix": 200,   "nb_personnes": 1,    "duree_semaines": 1},
    "Duo+":       {"prix": 400,   "nb_personnes": 3,    "duree_semaines": 1},
    "Famille+":   {"prix": 1000,  "nb_personnes": 5,    "duree_semaines": 1},
    "Entreprise": {"prix": None,  "nb_personnes": None, "duree_semaines": None},
}


# ─────────────────────────────────────────────
# SCHÉMAS Pydantic
# ─────────────────────────────────────────────

# ── AUTH ──
class RegisterIn(BaseModel):
    prenom: str
    nom: str
    email: EmailStr
    telephone: Optional[str] = None
    quartier: Optional[str] = None
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    prenom: str
    nom: str
    email: str
    is_admin: bool


class UserOut(BaseModel):
    id: str
    prenom: str
    nom: str
    email: str
    telephone: Optional[str]
    quartier: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateProfileIn(BaseModel):
    prenom: Optional[str] = None
    nom: Optional[str] = None
    telephone: Optional[str] = None
    quartier: Optional[str] = None


class ChangePasswordIn(BaseModel):
    ancien_mot_de_passe: str
    nouveau_mot_de_passe: str


# ── ABONNEMENTS ──
class AbonnementIn(BaseModel):
    plan: str
    nb_personnes: Optional[int] = 1
    personnes_couvertes: Optional[str] = None
    mode_paiement: Optional[str] = None
    notes: Optional[str] = None


class AbonnementOut(BaseModel):
    id: str
    user_id: str
    plan: str
    prix_semaine: Optional[float]
    nb_personnes: int
    personnes_couvertes: Optional[str]
    mode_paiement: Optional[str]
    statut: str
    date_souscription: datetime
    date_expiration: Optional[datetime]
    notes: Optional[str]

    class Config:
        from_attributes = True


class UpdateAbonnementStatut(BaseModel):
    statut: str


# ── INTERVENTIONS ──
class InterventionIn(BaseModel):
    type_urgence: str
    localisation: str
    description: Optional[str] = None
    eta_minutes: Optional[int] = None


class InterventionOut(BaseModel):
    id: str
    user_id: Optional[str]
    type_urgence: str
    localisation: str
    description: Optional[str]
    statut: str
    ambulance_id: Optional[str]
    eta_minutes: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpdateInterventionStatut(BaseModel):
    statut: str
    ambulance_id: Optional[str] = None
    eta_minutes: Optional[int] = None


# ── CONTACT ──
class ContactIn(BaseModel):
    prenom: str
    nom: str
    email: EmailStr
    telephone: Optional[str] = None
    objet: Optional[str] = None
    message: str


class ContactOut(BaseModel):
    id: str
    prenom: str
    nom: str
    email: str
    telephone: Optional[str]
    objet: Optional[str]
    message: str
    lu: bool
    repondu: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── EMPLOYÉS ──
class EmployeIn(BaseModel):
    prenom: str
    nom: str
    poste: str
    telephone: Optional[str] = None
    email: Optional[str] = None
    date_embauche: Optional[str] = None
    salaire_mensuel: Optional[float] = None
    heure_debut: Optional[str] = "08:00"
    notes: Optional[str] = None


class EmployeOut(BaseModel):
    id: str
    prenom: str
    nom: str
    poste: str
    telephone: Optional[str]
    email: Optional[str]
    date_embauche: Optional[str]
    salaire_mensuel: Optional[float]
    heure_debut: str
    statut: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── PRÉSENCES ──
class PresenceItem(BaseModel):
    employe_id: str
    heure_arrivee: Optional[str] = None
    statut: str
    motif: Optional[str] = None


class PresenceBatchIn(BaseModel):
    date: str
    presences: List[PresenceItem]


class PresenceOut(BaseModel):
    id: str
    employe_id: str
    date: str
    heure_arrivee: Optional[str]
    statut: str
    motif: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PresenceOutWithEmploye(PresenceOut):
    employe_prenom: Optional[str] = None
    employe_nom: Optional[str] = None
    employe_poste: Optional[str] = None


# ── FINANCES ──
class EntreeIn(BaseModel):
    date: str
    categorie: str
    motif: str
    payeur: Optional[str] = None
    methode_paiement: Optional[str] = None
    montant: float
    reference: Optional[str] = None


class EntreeOut(BaseModel):
    id: str
    date: str
    reference: Optional[str]
    categorie: str
    motif: str
    payeur: Optional[str]
    methode_paiement: Optional[str]
    montant: float
    created_at: datetime

    class Config:
        from_attributes = True


class SortieIn(BaseModel):
    date: str
    categorie: str
    motif: str
    beneficiaire: Optional[str] = None
    methode_paiement: Optional[str] = None
    montant: float
    reference: Optional[str] = None


class SortieOut(BaseModel):
    id: str
    date: str
    reference: Optional[str]
    categorie: str
    motif: str
    beneficiaire: Optional[str]
    methode_paiement: Optional[str]
    montant: float
    created_at: datetime

    class Config:
        from_attributes = True


# ── MEDIA ──
class ImageIn(BaseModel):
    titre: str
    categorie: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    visibilite: Optional[str] = "Publier sur le site"


class ImageOut(BaseModel):
    id: str
    titre: str
    categorie: Optional[str]
    url: Optional[str]
    description: Optional[str]
    visibilite: str
    created_at: datetime

    class Config:
        from_attributes = True


class VideoIn(BaseModel):
    titre: str
    categorie: Optional[str] = None
    url_source: Optional[str] = None
    type_source: Optional[str] = "youtube"
    duree: Optional[str] = None
    description: Optional[str] = None


class VideoOut(BaseModel):
    id: str
    titre: str
    categorie: Optional[str]
    url_source: Optional[str]
    type_source: str
    duree: Optional[str]
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ArticleIn(BaseModel):
    titre: str
    categorie: Optional[str] = None
    auteur: Optional[str] = None
    resume: Optional[str] = None
    contenu: Optional[str] = None
    tags: Optional[str] = None
    statut: Optional[str] = "Publier maintenant"
    image_url: Optional[str] = None


class ArticleOut(BaseModel):
    id: str
    titre: str
    categorie: Optional[str]
    auteur: Optional[str]
    resume: Optional[str]
    contenu: Optional[str]
    tags: Optional[str]
    statut: str
    image_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# ══ ROUTES AUTH  /auth ══
# ─────────────────────────────────────────────

@app.post("/auth/register", response_model=LoginOut, status_code=201, tags=["Auth"])
def register(data: RegisterIn, db: Session = Depends(get_db)):
    """Créer un nouveau compte utilisateur."""
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    user = User(
        prenom=data.prenom,
        nom=data.nom,
        email=data.email,
        telephone=data.telephone,
        quartier=data.quartier,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(
        {"sub": user.id}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return LoginOut(
        access_token=token, user_id=user.id, prenom=user.prenom,
        nom=user.nom, email=user.email, is_admin=user.is_admin
    )


@app.post("/auth/login", response_model=LoginOut, tags=["Auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Connexion avec email + mot de passe."""
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    token = create_access_token(
        {"sub": user.id}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return LoginOut(
        access_token=token, user_id=user.id, prenom=user.prenom,
        nom=user.nom, email=user.email, is_admin=user.is_admin
    )


@app.get("/auth/me", response_model=UserOut, tags=["Auth"])
def get_me(current_user: User = Depends(get_current_user)):
    """Récupérer le profil de l'utilisateur connecté."""
    return current_user


@app.patch("/auth/me", response_model=UserOut, tags=["Auth"])
def update_me(
    data: UpdateProfileIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour son profil."""
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@app.post("/auth/change-password", tags=["Auth"])
def change_password(
    data: ChangePasswordIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Changer son mot de passe."""
    if not verify_password(data.ancien_mot_de_passe, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Ancien mot de passe incorrect")
    current_user.hashed_password = hash_password(data.nouveau_mot_de_passe)
    db.commit()
    return {"message": "Mot de passe mis à jour avec succès"}


# ─────────────────────────────────────────────
# ══ ROUTES ABONNEMENTS  /abonnements ══
# ─────────────────────────────────────────────

@app.post("/abonnements", response_model=AbonnementOut, status_code=201, tags=["Abonnements"])
def creer_abonnement(
    data: AbonnementIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Souscrire à un plan d'abonnement."""
    if data.plan not in PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Plan invalide. Choisir parmi : {list(PLANS.keys())}"
        )
    plan_info = PLANS[data.plan]
    expiration = None
    if plan_info["duree_semaines"]:
        expiration = datetime.now(timezone.utc) + timedelta(weeks=plan_info["duree_semaines"])

    abo = Abonnement(
        user_id=current_user.id,
        plan=data.plan,
        prix_semaine=plan_info["prix"],
        nb_personnes=data.nb_personnes or plan_info.get("nb_personnes") or 1,
        personnes_couvertes=data.personnes_couvertes,
        mode_paiement=data.mode_paiement,
        statut="en_attente",
        date_expiration=expiration,
        notes=data.notes,
    )
    db.add(abo)
    db.commit()
    db.refresh(abo)
    return abo


@app.get("/abonnements/mes", response_model=List[AbonnementOut], tags=["Abonnements"])
def mes_abonnements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lister tous mes abonnements (utilisateur connecté)."""
    return (
        db.query(Abonnement)
        .filter(Abonnement.user_id == current_user.id)
        .order_by(Abonnement.date_souscription.desc())
        .all()
    )


@app.get("/abonnements/{abo_id}", response_model=AbonnementOut, tags=["Abonnements"])
def get_abonnement(
    abo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Détail d'un abonnement."""
    abo = db.query(Abonnement).filter(Abonnement.id == abo_id).first()
    if not abo:
        raise HTTPException(status_code=404, detail="Abonnement introuvable")
    if abo.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès refusé")
    return abo


@app.delete("/abonnements/{abo_id}", status_code=204, tags=["Abonnements"])
def annuler_abonnement(
    abo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Annuler un abonnement."""
    abo = db.query(Abonnement).filter(Abonnement.id == abo_id).first()
    if not abo:
        raise HTTPException(status_code=404, detail="Abonnement introuvable")
    if abo.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès refusé")
    abo.statut = "annulé"
    db.commit()


# ─────────────────────────────────────────────
# ══ ROUTES INTERVENTIONS  /interventions ══
# ─────────────────────────────────────────────

@app.post("/interventions", response_model=InterventionOut, status_code=201, tags=["Interventions"])
def declarer_intervention(
    data: InterventionIn,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Déclarer une intervention d'urgence (accessible sans authentification)."""
    interv = Intervention(
        user_id=current_user.id if current_user else None,
        type_urgence=data.type_urgence,
        localisation=data.localisation,
        description=data.description,
        statut="urgence",
        eta_minutes=data.eta_minutes,
    )
    db.add(interv)
    db.commit()
    db.refresh(interv)
    return interv


@app.get("/interventions/actives", response_model=List[InterventionOut], tags=["Interventions"])
def interventions_actives(db: Session = Depends(get_db)):
    """Interventions en cours — tableau de bord live (public)."""
    return (
        db.query(Intervention)
        .filter(Intervention.statut.in_(["urgence", "enroute", "transit"]))
        .order_by(Intervention.created_at.desc())
        .limit(10)
        .all()
    )


@app.get("/interventions/historique", response_model=List[InterventionOut], tags=["Interventions"])
def historique_interventions(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Historique des interventions."""
    q = db.query(Intervention)
    if not current_user.is_admin:
        q = q.filter(Intervention.user_id == current_user.id)
    return q.order_by(Intervention.created_at.desc()).offset(skip).limit(limit).all()


@app.patch("/interventions/{interv_id}/statut", response_model=InterventionOut, tags=["Interventions"])
def maj_statut_intervention(
    interv_id: str,
    data: UpdateInterventionStatut,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour le statut d'une intervention (admin)."""
    interv = db.query(Intervention).filter(Intervention.id == interv_id).first()
    if not interv:
        raise HTTPException(status_code=404, detail="Intervention introuvable")
    interv.statut = data.statut
    if data.ambulance_id:
        interv.ambulance_id = data.ambulance_id
    if data.eta_minutes is not None:
        interv.eta_minutes = data.eta_minutes
    interv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(interv)
    return interv


# ─────────────────────────────────────────────
# ══ ROUTES CONTACT  /contact ══
# ─────────────────────────────────────────────

@app.post("/contact", response_model=ContactOut, status_code=201, tags=["Contact"])
def envoyer_message(data: ContactIn, db: Session = Depends(get_db)):
    """Envoyer un message via le formulaire de contact (public)."""
    msg = Contact(
        prenom=data.prenom,
        nom=data.nom,
        email=data.email,
        telephone=data.telephone,
        objet=data.objet,
        message=data.message,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@app.get("/contact", response_model=List[ContactOut], tags=["Contact"])
def lister_messages(
    lu: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lister les messages de contact (admin)."""
    q = db.query(Contact)
    if lu is not None:
        q = q.filter(Contact.lu == lu)
    return q.order_by(Contact.created_at.desc()).offset(skip).limit(limit).all()


@app.patch("/contact/{msg_id}/lu", response_model=ContactOut, tags=["Contact"])
def marquer_lu(
    msg_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Marquer un message comme lu (admin)."""
    msg = db.query(Contact).filter(Contact.id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message introuvable")
    msg.lu = True
    db.commit()
    db.refresh(msg)
    return msg


@app.patch("/contact/{msg_id}/repondu", response_model=ContactOut, tags=["Contact"])
def marquer_repondu(
    msg_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Marquer un message comme répondu (admin)."""
    msg = db.query(Contact).filter(Contact.id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message introuvable")
    msg.lu = True
    msg.repondu = True
    db.commit()
    db.refresh(msg)
    return msg


@app.delete("/contact/{msg_id}", status_code=204, tags=["Contact"])
def supprimer_message(
    msg_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Supprimer un message de contact (admin)."""
    msg = db.query(Contact).filter(Contact.id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message introuvable")
    db.delete(msg)
    db.commit()


# ─────────────────────────────────────────────
# ══ ROUTES RH  /rh ══
# ─────────────────────────────────────────────

@app.post("/rh/employes", response_model=EmployeOut, status_code=201, tags=["RH"])
def ajouter_employe(
    data: EmployeIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Ajouter un employé."""
    emp = Employe(**data.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@app.get("/rh/employes", response_model=List[EmployeOut], tags=["RH"])
def lister_employes(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lister tous les employés."""
    return db.query(Employe).order_by(Employe.created_at.desc()).all()


@app.get("/rh/employes/{emp_id}", response_model=EmployeOut, tags=["RH"])
def get_employe(
    emp_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    emp = db.query(Employe).filter(Employe.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    return emp


@app.patch("/rh/employes/{emp_id}", response_model=EmployeOut, tags=["RH"])
def modifier_employe(
    emp_id: str,
    data: EmployeIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Modifier un employé."""
    emp = db.query(Employe).filter(Employe.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    db.commit()
    db.refresh(emp)
    return emp


@app.delete("/rh/employes/{emp_id}", status_code=204, tags=["RH"])
def supprimer_employe(
    emp_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Supprimer un employé."""
    emp = db.query(Employe).filter(Employe.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    db.delete(emp)
    db.commit()


# ── PRÉSENCES ──

@app.post("/rh/presences/batch", response_model=List[PresenceOut], status_code=201, tags=["RH"])
def enregistrer_presences(
    data: PresenceBatchIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Enregistrer les présences de tous les employés pour une date donnée.
    Si une présence existe déjà pour cet employé/date, elle est mise à jour.
    """
    results = []
    for item in data.presences:
        existing = (
            db.query(Presence)
            .filter(Presence.employe_id == item.employe_id, Presence.date == data.date)
            .first()
        )
        if existing:
            existing.heure_arrivee = item.heure_arrivee
            existing.statut = item.statut
            existing.motif = item.motif
            db.commit()
            db.refresh(existing)
            results.append(existing)
        else:
            p = Presence(
                employe_id=item.employe_id,
                date=data.date,
                heure_arrivee=item.heure_arrivee,
                statut=item.statut,
                motif=item.motif,
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            results.append(p)
    return results


@app.get("/rh/presences", response_model=List[PresenceOutWithEmploye], tags=["RH"])
def lister_presences(
    date: Optional[str] = None,
    employe_id: Optional[str] = None,
    statut: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lister les présences avec filtres optionnels (date, employé, statut)."""
    q = db.query(Presence, Employe).join(Employe, Presence.employe_id == Employe.id)
    if date:
        q = q.filter(Presence.date == date)
    if employe_id:
        q = q.filter(Presence.employe_id == employe_id)
    if statut:
        q = q.filter(Presence.statut == statut)
    rows = q.order_by(Presence.date.desc(), Employe.nom).all()
    result = []
    for presence, employe in rows:
        row = PresenceOutWithEmploye(
            id=presence.id,
            employe_id=presence.employe_id,
            date=presence.date,
            heure_arrivee=presence.heure_arrivee,
            statut=presence.statut,
            motif=presence.motif,
            created_at=presence.created_at,
            employe_prenom=employe.prenom,
            employe_nom=employe.nom,
            employe_poste=employe.poste,
        )
        result.append(row)
    return result


@app.patch("/rh/presences/{presence_id}", response_model=PresenceOut, tags=["RH"])
def modifier_presence(
    presence_id: str,
    data: PresenceItem,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Modifier une présence individuelle."""
    p = db.query(Presence).filter(Presence.id == presence_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Présence introuvable")
    p.heure_arrivee = data.heure_arrivee
    p.statut = data.statut
    p.motif = data.motif
    db.commit()
    db.refresh(p)
    return p


@app.delete("/rh/presences/{presence_id}", status_code=204, tags=["RH"])
def supprimer_presence(
    presence_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    p = db.query(Presence).filter(Presence.id == presence_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Présence introuvable")
    db.delete(p)
    db.commit()


@app.get("/rh/stats", tags=["RH"])
def rh_stats(
    date: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Statistiques RH pour une date (défaut = aujourd'hui)."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    total_employes = db.query(Employe).filter(Employe.statut == "active").count()
    presences_jour = db.query(Presence).filter(Presence.date == target_date).all()
    presents = sum(1 for p in presences_jour if p.statut == "present")
    absents = sum(1 for p in presences_jour if p.statut == "absent")
    retards = sum(1 for p in presences_jour if p.statut == "retard")
    return {
        "date": target_date,
        "total_employes": total_employes,
        "presents": presents,
        "absents": absents,
        "retards": retards,
        "taux_presence": round((presents / total_employes * 100) if total_employes else 0, 1),
    }


# ─────────────────────────────────────────────
# ══ ROUTES FINANCES  /finance ══
# ─────────────────────────────────────────────

@app.post("/finance/entrees", response_model=EntreeOut, status_code=201, tags=["Finance"])
def ajouter_entree(
    data: EntreeIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Enregistrer une entrée financière."""
    if not data.reference:
        count = db.query(EntreeFinanciere).count()
        data.reference = f"REC-{datetime.now().year}-{str(count + 1).zfill(4)}"
    entree = EntreeFinanciere(**data.model_dump())
    db.add(entree)
    db.commit()
    db.refresh(entree)
    return entree


@app.get("/finance/entrees", response_model=List[EntreeOut], tags=["Finance"])
def lister_entrees(
    mois: Optional[str] = None,          # format YYYY-MM
    categorie: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lister les entrées financières."""
    q = db.query(EntreeFinanciere)
    if mois:
        q = q.filter(EntreeFinanciere.date.startswith(mois))
    if categorie:
        q = q.filter(EntreeFinanciere.categorie == categorie)
    return q.order_by(EntreeFinanciere.date.desc()).offset(skip).limit(limit).all()


@app.patch("/finance/entrees/{entree_id}", response_model=EntreeOut, tags=["Finance"])
def modifier_entree(
    entree_id: str,
    data: EntreeIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    entree = db.query(EntreeFinanciere).filter(EntreeFinanciere.id == entree_id).first()
    if not entree:
        raise HTTPException(status_code=404, detail="Entrée introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(entree, field, value)
    db.commit()
    db.refresh(entree)
    return entree


@app.delete("/finance/entrees/{entree_id}", status_code=204, tags=["Finance"])
def supprimer_entree(
    entree_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    entree = db.query(EntreeFinanciere).filter(EntreeFinanciere.id == entree_id).first()
    if not entree:
        raise HTTPException(status_code=404, detail="Entrée introuvable")
    db.delete(entree)
    db.commit()


@app.post("/finance/sorties", response_model=SortieOut, status_code=201, tags=["Finance"])
def ajouter_sortie(
    data: SortieIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Enregistrer une sortie financière."""
    if not data.reference:
        count = db.query(SortieFinanciere).count()
        data.reference = f"BON-{datetime.now().year}-{str(count + 1).zfill(4)}"
    sortie = SortieFinanciere(**data.model_dump())
    db.add(sortie)
    db.commit()
    db.refresh(sortie)
    return sortie


@app.get("/finance/sorties", response_model=List[SortieOut], tags=["Finance"])
def lister_sorties(
    mois: Optional[str] = None,
    categorie: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lister les sorties financières."""
    q = db.query(SortieFinanciere)
    if mois:
        q = q.filter(SortieFinanciere.date.startswith(mois))
    if categorie:
        q = q.filter(SortieFinanciere.categorie == categorie)
    return q.order_by(SortieFinanciere.date.desc()).offset(skip).limit(limit).all()


@app.patch("/finance/sorties/{sortie_id}", response_model=SortieOut, tags=["Finance"])
def modifier_sortie(
    sortie_id: str,
    data: SortieIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    sortie = db.query(SortieFinanciere).filter(SortieFinanciere.id == sortie_id).first()
    if not sortie:
        raise HTTPException(status_code=404, detail="Sortie introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(sortie, field, value)
    db.commit()
    db.refresh(sortie)
    return sortie


@app.delete("/finance/sorties/{sortie_id}", status_code=204, tags=["Finance"])
def supprimer_sortie(
    sortie_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    sortie = db.query(SortieFinanciere).filter(SortieFinanciere.id == sortie_id).first()
    if not sortie:
        raise HTTPException(status_code=404, detail="Sortie introuvable")
    db.delete(sortie)
    db.commit()


@app.get("/finance/bilan", tags=["Finance"])
def bilan_financier(
    mois: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Bilan financier (total entrées, sorties, solde net)."""
    qe = db.query(func.sum(EntreeFinanciere.montant))
    qs = db.query(func.sum(SortieFinanciere.montant))
    if mois:
        qe = qe.filter(EntreeFinanciere.date.startswith(mois))
        qs = qs.filter(SortieFinanciere.date.startswith(mois))
    total_entrees = qe.scalar() or 0.0
    total_sorties = qs.scalar() or 0.0
    return {
        "mois": mois or "global",
        "total_entrees": total_entrees,
        "total_sorties": total_sorties,
        "solde_net": total_entrees - total_sorties,
        "nb_entrees": db.query(EntreeFinanciere).count(),
        "nb_sorties": db.query(SortieFinanciere).count(),
    }


# ─────────────────────────────────────────────
# ══ ROUTES MEDIA  /media ══
# ─────────────────────────────────────────────

# ── Images ──
@app.post("/media/images", response_model=ImageOut, status_code=201, tags=["Media"])
def ajouter_image(
    data: ImageIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    img = Image(**data.model_dump())
    db.add(img)
    db.commit()
    db.refresh(img)
    return img


@app.get("/media/images", response_model=List[ImageOut], tags=["Media"])
def lister_images(db: Session = Depends(get_db)):
    """Lister toutes les images publiées (public)."""
    return db.query(Image).order_by(Image.created_at.desc()).all()


@app.patch("/media/images/{img_id}", response_model=ImageOut, tags=["Media"])
def modifier_image(
    img_id: str,
    data: ImageIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    img = db.query(Image).filter(Image.id == img_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(img, field, value)
    db.commit()
    db.refresh(img)
    return img


@app.delete("/media/images/{img_id}", status_code=204, tags=["Media"])
def supprimer_image(
    img_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    img = db.query(Image).filter(Image.id == img_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image introuvable")
    db.delete(img)
    db.commit()


# ── Vidéos ──
@app.post("/media/videos", response_model=VideoOut, status_code=201, tags=["Media"])
def ajouter_video(
    data: VideoIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    vid = Video(**data.model_dump())
    db.add(vid)
    db.commit()
    db.refresh(vid)
    return vid


@app.get("/media/videos", response_model=List[VideoOut], tags=["Media"])
def lister_videos(db: Session = Depends(get_db)):
    """Lister toutes les vidéos (public)."""
    return db.query(Video).order_by(Video.created_at.desc()).all()


@app.patch("/media/videos/{vid_id}", response_model=VideoOut, tags=["Media"])
def modifier_video(
    vid_id: str,
    data: VideoIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    vid = db.query(Video).filter(Video.id == vid_id).first()
    if not vid:
        raise HTTPException(status_code=404, detail="Vidéo introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(vid, field, value)
    db.commit()
    db.refresh(vid)
    return vid


@app.delete("/media/videos/{vid_id}", status_code=204, tags=["Media"])
def supprimer_video(
    vid_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    vid = db.query(Video).filter(Video.id == vid_id).first()
    if not vid:
        raise HTTPException(status_code=404, detail="Vidéo introuvable")
    db.delete(vid)
    db.commit()


# ── Articles / Blog ──
@app.post("/media/articles", response_model=ArticleOut, status_code=201, tags=["Media"])
def ajouter_article(
    data: ArticleIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    article = Article(**data.model_dump())
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


@app.get("/media/articles", response_model=List[ArticleOut], tags=["Media"])
def lister_articles(
    statut: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lister les articles (public – filtre statut optionnel)."""
    q = db.query(Article)
    if statut:
        q = q.filter(Article.statut == statut)
    return q.order_by(Article.created_at.desc()).all()


@app.patch("/media/articles/{art_id}", response_model=ArticleOut, tags=["Media"])
def modifier_article(
    art_id: str,
    data: ArticleIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    art = db.query(Article).filter(Article.id == art_id).first()
    if not art:
        raise HTTPException(status_code=404, detail="Article introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(art, field, value)
    db.commit()
    db.refresh(art)
    return art


@app.delete("/media/articles/{art_id}", status_code=204, tags=["Media"])
def supprimer_article(
    art_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    art = db.query(Article).filter(Article.id == art_id).first()
    if not art:
        raise HTTPException(status_code=404, detail="Article introuvable")
    db.delete(art)
    db.commit()


# ─────────────────────────────────────────────
# ══ ROUTES ADMIN  /admin ══
# ─────────────────────────────────────────────

@app.get("/admin/stats", tags=["Admin"])
def statistiques_globales(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Tableau de bord — statistiques globales."""
    today = datetime.now().strftime("%Y-%m-%d")
    mois_en_cours = datetime.now().strftime("%Y-%m")

    total_users = db.query(User).count()
    abos_actifs = db.query(Abonnement).filter(Abonnement.statut == "actif").count()
    abos_en_attente = db.query(Abonnement).filter(Abonnement.statut == "en_attente").count()
    abos_total = db.query(Abonnement).count()

    interventions_actives = db.query(Intervention).filter(
        Intervention.statut.in_(["urgence", "enroute", "transit"])
    ).count()
    interventions_total = db.query(Intervention).count()

    messages_non_lus = db.query(Contact).filter(Contact.lu == False).count()
    messages_total = db.query(Contact).count()

    total_employes = db.query(Employe).filter(Employe.statut == "active").count()
    presences_today = db.query(Presence).filter(Presence.date == today).all()
    presents_today = sum(1 for p in presences_today if p.statut == "present")

    # Finances du mois en cours
    total_entrees = db.query(func.sum(EntreeFinanciere.montant)).filter(
        EntreeFinanciere.date.startswith(mois_en_cours)
    ).scalar() or 0.0
    total_sorties = db.query(func.sum(SortieFinanciere.montant)).filter(
        SortieFinanciere.date.startswith(mois_en_cours)
    ).scalar() or 0.0

    return {
        "utilisateurs": {
            "total": total_users,
            "nouveaux_semaine": db.query(User).filter(
                User.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
            ).count(),
        },
        "abonnements": {
            "actifs": abos_actifs,
            "en_attente": abos_en_attente,
            "total": abos_total,
        },
        "interventions": {
            "actives": interventions_actives,
            "total": interventions_total,
        },
        "contact": {
            "non_lus": messages_non_lus,
            "total": messages_total,
        },
        "rh": {
            "total_employes": total_employes,
            "presents_aujourd_hui": presents_today,
        },
        "finance": {
            "mois": mois_en_cours,
            "total_entrees": total_entrees,
            "total_sorties": total_sorties,
            "solde_net": total_entrees - total_sorties,
        },
    }


@app.get("/admin/users", response_model=List[UserOut], tags=["Admin"])
def lister_users(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lister tous les utilisateurs (avec recherche optionnelle)."""
    q = db.query(User)
    if search:
        q = q.filter(
            User.nom.ilike(f"%{search}%")
            | User.prenom.ilike(f"%{search}%")
            | User.email.ilike(f"%{search}%")
        )
    return q.order_by(User.created_at.desc()).offset(skip).limit(limit).all()


@app.get("/admin/users/{user_id}", response_model=UserOut, tags=["Admin"])
def get_user(
    user_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user


@app.patch("/admin/users/{user_id}", response_model=UserOut, tags=["Admin"])
def modifier_user(
    user_id: str,
    data: UpdateProfileIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Modifier un utilisateur (admin)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@app.delete("/admin/users/{user_id}", status_code=204, tags=["Admin"])
def supprimer_user(
    user_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Supprimer un utilisateur."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    db.delete(user)
    db.commit()


@app.get("/admin/abonnements", response_model=List[AbonnementOut], tags=["Admin"])
def lister_abonnements_admin(
    statut: Optional[str] = None,
    plan: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lister tous les abonnements (admin)."""
    q = db.query(Abonnement)
    if statut:
        q = q.filter(Abonnement.statut == statut)
    if plan:
        q = q.filter(Abonnement.plan == plan)
    return q.order_by(Abonnement.date_souscription.desc()).offset(skip).limit(limit).all()


@app.patch("/admin/abonnements/{abo_id}/statut", response_model=AbonnementOut, tags=["Admin"])
def admin_maj_abonnement(
    abo_id: str,
    data: UpdateAbonnementStatut,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Activer / suspendre / annuler un abonnement (admin)."""
    abo = db.query(Abonnement).filter(Abonnement.id == abo_id).first()
    if not abo:
        raise HTTPException(status_code=404, detail="Abonnement introuvable")
    abo.statut = data.statut
    if data.statut == "actif" and not abo.date_expiration:
        abo.date_expiration = datetime.now(timezone.utc) + timedelta(weeks=1)
    db.commit()
    db.refresh(abo)
    return abo


@app.delete("/admin/abonnements/{abo_id}", status_code=204, tags=["Admin"])
def supprimer_abonnement_admin(
    abo_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    abo = db.query(Abonnement).filter(Abonnement.id == abo_id).first()
    if not abo:
        raise HTTPException(status_code=404, detail="Abonnement introuvable")
    db.delete(abo)
    db.commit()


@app.patch("/admin/users/{user_id}/toggle-admin", response_model=UserOut, tags=["Admin"])
def toggle_admin(
    user_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Accorder ou retirer les droits admin à un utilisateur."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.is_admin = not user.is_admin
    db.commit()
    db.refresh(user)
    return user


# ─────────────────────────────────────────────
# ROUTE RACINE
# ─────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": "Secours Abalo API",
        "version": "2.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "urgence": "8880",
        "status": "running",
    }


class ProfilMedical(Base):
    __tablename__ = "profils_medicaux"

    id                  = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id             = Column(String, ForeignKey("users.id"), nullable=False, unique=True)

    # Identité complète
    date_naissance      = Column(String, nullable=True)
    sexe                = Column(String, nullable=True)
    nationalite         = Column(String, nullable=True)
    profession          = Column(String, nullable=True)
    region              = Column(String, nullable=True)
    quartier            = Column(String, nullable=True)
    adresse_domicile    = Column(String, nullable=True)
    adresse_travail     = Column(String, nullable=True)

    # Localisation GPS
    lat_domicile        = Column(Float, nullable=True)
    lng_domicile        = Column(Float, nullable=True)
    lat_travail         = Column(Float, nullable=True)
    lng_travail         = Column(Float, nullable=True)

    # Données médicales
    groupe_sanguin      = Column(String, nullable=True)
    taille_cm           = Column(Integer, nullable=True)
    poids_kg            = Column(Float, nullable=True)
    maladies            = Column(Text, nullable=True)   # JSON string : ["Hypertension"]
    allergies           = Column(Text, nullable=True)   # JSON string : ["Pénicilline"]
    medicaments         = Column(Text, nullable=True)   # JSON string : ["Amlodipine 5mg"]
    antecedents_familiaux = Column(Text, nullable=True)
    medecin_referent    = Column(String, nullable=True)

    # Mode de vie
    fumeur              = Column(String, nullable=True)  # Jamais | Non | Oui | Ancien
    alcool              = Column(String, nullable=True)  # Non | Occasionnel | Régulier
    activite_physique   = Column(String, nullable=True)
    regime_alimentaire  = Column(String, nullable=True)
    infos_complementaires = Column(Text, nullable=True)

    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="profil_medical", uselist=False)


class ContactUrgenceClient(Base):
    __tablename__ = "contacts_urgence_clients"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    prenom_nom  = Column(String, nullable=False)
    lien        = Column(String, nullable=True)   # Sœur, Ami, Collègue…
    telephone   = Column(String, nullable=False)
    telephone2  = Column(String, nullable=True)
    priorite    = Column(Integer, default=1)       # 1 = contact principal
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="contacts_urgence")


class LocalisationClient(Base):
    __tablename__ = "localisations_clients"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    latitude    = Column(Float, nullable=False)
    longitude   = Column(Float, nullable=False)
    precision_m = Column(Float, nullable=True)
    source      = Column(String, default="gps")    # gps | manuelle
    envoyee_a   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    est_sos     = Column(Boolean, default=False)    # True si envoyée pendant un SOS

    user = relationship("User", backref="localisations")


class SOSAlerte(Base):
    __tablename__ = "sos_alertes"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id         = Column(String, ForeignKey("users.id"), nullable=True)
    # Snapshot infos client au moment du SOS (dénormalisé pour accès rapide admin)
    nom_complet     = Column(String, nullable=True)
    telephone       = Column(String, nullable=True)
    groupe_sanguin  = Column(String, nullable=True)
    allergies       = Column(Text, nullable=True)
    maladies        = Column(Text, nullable=True)
    medicaments     = Column(Text, nullable=True)
    medecin_referent = Column(String, nullable=True)
    latitude        = Column(Float, nullable=True)
    longitude       = Column(Float, nullable=True)
    adresse         = Column(String, nullable=True)
    statut          = Column(String, default="actif")  # actif | pris_en_charge | termine
    note_urgence    = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="sos_alertes")


class NotificationClient(Base):
    __tablename__ = "notifications_clients"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    titre       = Column(String, nullable=False)
    message     = Column(Text, nullable=False)
    type        = Column(String, default="info")   # info | success | warning | danger
    icone       = Column(String, nullable=True)
    lue         = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="notifications")


# Créez les nouvelles tables (à appeler après Base.metadata.create_all existant)
# Base.metadata.create_all(bind=engine)   ← déjà présent dans votre main.py


# =============================================================
# SECTION 2 : SCHÉMAS PYDANTIC SUPPLÉMENTAIRES
# Collez ces classes avec vos autres classes Pydantic
# =============================================================

class ProfilMedicalIn(BaseModel):
    date_naissance:     Optional[str]   = None
    sexe:               Optional[str]   = None
    nationalite:        Optional[str]   = None
    profession:         Optional[str]   = None
    region:             Optional[str]   = None
    quartier:           Optional[str]   = None
    adresse_domicile:   Optional[str]   = None
    adresse_travail:    Optional[str]   = None
    lat_domicile:       Optional[float] = None
    lng_domicile:       Optional[float] = None
    lat_travail:        Optional[float] = None
    lng_travail:        Optional[float] = None
    groupe_sanguin:     Optional[str]   = None
    taille_cm:          Optional[int]   = None
    poids_kg:           Optional[float] = None
    maladies:           Optional[str]   = None
    allergies:          Optional[str]   = None
    medicaments:        Optional[str]   = None
    antecedents_familiaux: Optional[str] = None
    medecin_referent:   Optional[str]   = None
    fumeur:             Optional[str]   = None
    alcool:             Optional[str]   = None
    activite_physique:  Optional[str]   = None
    regime_alimentaire: Optional[str]   = None
    infos_complementaires: Optional[str] = None


class ProfilMedicalOut(ProfilMedicalIn):
    id:         str
    user_id:    str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class ContactUrgenceIn(BaseModel):
    prenom_nom:  str
    lien:        Optional[str] = None
    telephone:   str
    telephone2:  Optional[str] = None
    priorite:    Optional[int] = 1


class ContactUrgenceOut(ContactUrgenceIn):
    id:         str
    user_id:    str
    created_at: datetime
    class Config:
        from_attributes = True


class LocalisationIn(BaseModel):
    latitude:    float
    longitude:   float
    precision_m: Optional[float] = None
    source:      Optional[str]   = "gps"
    est_sos:     Optional[bool]  = False


class LocalisationOut(LocalisationIn):
    id:         str
    user_id:    str
    envoyee_a:  datetime
    class Config:
        from_attributes = True


class SOSAlerteIn(BaseModel):
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None
    adresse:     Optional[str]   = None
    note_urgence: Optional[str]  = None


class SOSAlerteOut(BaseModel):
    id:              str
    user_id:         Optional[str]
    nom_complet:     Optional[str]
    telephone:       Optional[str]
    groupe_sanguin:  Optional[str]
    allergies:       Optional[str]
    maladies:        Optional[str]
    medicaments:     Optional[str]
    medecin_referent: Optional[str]
    latitude:        Optional[float]
    longitude:       Optional[float]
    adresse:         Optional[str]
    statut:          str
    note_urgence:    Optional[str]
    created_at:      datetime
    class Config:
        from_attributes = True


class NotificationOut(BaseModel):
    id:         str
    user_id:    str
    titre:      str
    message:    str
    type:       str
    icone:      Optional[str]
    lue:        bool
    created_at: datetime
    class Config:
        from_attributes = True


# =============================================================
# SECTION 3 : ROUTES CLIENT /client
# Collez TOUTES ces routes dans votre app FastAPI existante
# =============================================================

# ── Profil médical ──────────────────────────────────────────

@app.get("/client/profil-medical", response_model=ProfilMedicalOut, tags=["Client"])
def get_profil_medical(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupérer le profil médical de l'utilisateur connecté."""
    profil = db.query(ProfilMedical).filter(
        ProfilMedical.user_id == current_user.id
    ).first()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil médical non trouvé")
    return profil


@app.put("/client/profil-medical", response_model=ProfilMedicalOut, tags=["Client"])
def upsert_profil_medical(
    data: ProfilMedicalIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Créer ou mettre à jour le profil médical complet."""
    profil = db.query(ProfilMedical).filter(
        ProfilMedical.user_id == current_user.id
    ).first()

    if profil:
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(profil, field, value)
        profil.updated_at = datetime.now(timezone.utc)
    else:
        profil = ProfilMedical(
            user_id=current_user.id,
            **data.model_dump(exclude_none=True)
        )
        db.add(profil)

    db.commit()
    db.refresh(profil)
    return profil


@app.patch("/client/profil-medical/identite", response_model=ProfilMedicalOut, tags=["Client"])
def update_identite(
    data: ProfilMedicalIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour uniquement la section Identité."""
    champs_identite = {
        "date_naissance", "sexe", "nationalite", "profession",
        "region", "quartier", "adresse_domicile", "adresse_travail"
    }
    profil = _get_or_create_profil(current_user.id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        if field in champs_identite:
            setattr(profil, field, value)
    profil.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profil)
    return profil


@app.patch("/client/profil-medical/localisation", response_model=ProfilMedicalOut, tags=["Client"])
def update_localisation_profil(
    data: ProfilMedicalIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour les coordonnées GPS domicile / travail."""
    champs_gps = {"lat_domicile", "lng_domicile", "lat_travail", "lng_travail",
                   "adresse_domicile", "adresse_travail"}
    profil = _get_or_create_profil(current_user.id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        if field in champs_gps:
            setattr(profil, field, value)
    profil.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profil)
    return profil


@app.patch("/client/profil-medical/medical", response_model=ProfilMedicalOut, tags=["Client"])
def update_medical(
    data: ProfilMedicalIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour les informations médicales (groupe sanguin, allergies, etc.)."""
    champs_med = {
        "groupe_sanguin", "taille_cm", "poids_kg", "maladies",
        "allergies", "medicaments", "antecedents_familiaux", "medecin_referent"
    }
    profil = _get_or_create_profil(current_user.id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        if field in champs_med:
            setattr(profil, field, value)
    profil.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profil)
    return profil


@app.patch("/client/profil-medical/mode-de-vie", response_model=ProfilMedicalOut, tags=["Client"])
def update_mode_de_vie(
    data: ProfilMedicalIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour la section Mode de vie."""
    champs_vie = {"fumeur", "alcool", "activite_physique",
                   "regime_alimentaire", "infos_complementaires"}
    profil = _get_or_create_profil(current_user.id, db)
    for field, value in data.model_dump(exclude_none=True).items():
        if field in champs_vie:
            setattr(profil, field, value)
    profil.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profil)
    return profil


def _get_or_create_profil(user_id: str, db: Session) -> ProfilMedical:
    """Helper : retourne le profil médical ou en crée un vide."""
    profil = db.query(ProfilMedical).filter(
        ProfilMedical.user_id == user_id
    ).first()
    if not profil:
        profil = ProfilMedical(user_id=user_id)
        db.add(profil)
        db.commit()
        db.refresh(profil)
    return profil


# ── Contacts d'urgence client ────────────────────────────────

@app.get("/client/contacts-urgence", response_model=List[ContactUrgenceOut], tags=["Client"])
def mes_contacts_urgence(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lister mes contacts d'urgence triés par priorité."""
    return (
        db.query(ContactUrgenceClient)
        .filter(ContactUrgenceClient.user_id == current_user.id)
        .order_by(ContactUrgenceClient.priorite)
        .all()
    )


@app.post("/client/contacts-urgence", response_model=ContactUrgenceOut, status_code=201, tags=["Client"])
def ajouter_contact_urgence(
    data: ContactUrgenceIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ajouter un contact d'urgence."""
    contact = ContactUrgenceClient(user_id=current_user.id, **data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@app.patch("/client/contacts-urgence/{contact_id}", response_model=ContactUrgenceOut, tags=["Client"])
def modifier_contact_urgence(
    contact_id: str,
    data: ContactUrgenceIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Modifier un contact d'urgence."""
    contact = db.query(ContactUrgenceClient).filter(
        ContactUrgenceClient.id == contact_id,
        ContactUrgenceClient.user_id == current_user.id
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@app.delete("/client/contacts-urgence/{contact_id}", status_code=204, tags=["Client"])
def supprimer_contact_urgence(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprimer un contact d'urgence."""
    contact = db.query(ContactUrgenceClient).filter(
        ContactUrgenceClient.id == contact_id,
        ContactUrgenceClient.user_id == current_user.id
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    db.delete(contact)
    db.commit()


# ── Localisation en temps réel ───────────────────────────────

@app.post("/client/localisation", response_model=LocalisationOut, status_code=201, tags=["Client"])
def envoyer_localisation(
    data: LocalisationIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Envoyer la position GPS actuelle aux équipes Secours Abalo."""
    loc = LocalisationClient(user_id=current_user.id, **data.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)

    # Créer une notification automatique pour l'admin (visible côté admin)
    notif_admin_data = {
        "user_id": current_user.id,
        "titre":   "Position GPS reçue",
        "message": f"{current_user.prenom} {current_user.nom} a envoyé sa position "
                   f"({data.latitude:.5f}, {data.longitude:.5f})"
                   + (" – SOS ACTIF" if data.est_sos else ""),
        "type": "danger" if data.est_sos else "info",
        "icone": "fa-location-dot",
    }
    # (Ici vous pouvez brancher WebSocket ou Pusher pour le temps réel)

    return loc


@app.get("/client/localisation/historique", response_model=List[LocalisationOut], tags=["Client"])
def historique_localisations(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Historique de mes envois de position."""
    return (
        db.query(LocalisationClient)
        .filter(LocalisationClient.user_id == current_user.id)
        .order_by(LocalisationClient.envoyee_a.desc())
        .limit(limit)
        .all()
    )


# ── SOS Alertes ─────────────────────────────────────────────

@app.post("/client/sos", response_model=SOSAlerteOut, status_code=201, tags=["Client – SOS"])
def declencher_sos(
    data: SOSAlerteIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Déclenche un SOS :
    1. Crée une alerte avec snapshot des données médicales du client
    2. Enregistre la position si fournie
    3. Crée des notifications pour l'admin et le client
    Côté admin, cette alerte apparaît immédiatement dans le dashboard.
    """
    # Récupérer le profil médical pour le snapshot
    profil = db.query(ProfilMedical).filter(
        ProfilMedical.user_id == current_user.id
    ).first()

    # Récupérer l'abonnement actif
    abo = db.query(Abonnement).filter(
        Abonnement.user_id == current_user.id,
        Abonnement.statut == "actif"
    ).order_by(Abonnement.date_souscription.desc()).first()

    alerte = SOSAlerte(
        user_id=current_user.id,
        nom_complet=f"{current_user.prenom} {current_user.nom}",
        telephone=current_user.telephone,
        groupe_sanguin=profil.groupe_sanguin if profil else None,
        allergies=profil.allergies if profil else None,
        maladies=profil.maladies if profil else None,
        medicaments=profil.medicaments if profil else None,
        medecin_referent=profil.medecin_referent if profil else None,
        latitude=data.latitude,
        longitude=data.longitude,
        adresse=data.adresse or (profil.adresse_domicile if profil else None),
        note_urgence=data.note_urgence,
        statut="actif",
    )
    db.add(alerte)

    # Sauvegarder la localisation liée au SOS
    if data.latitude and data.longitude:
        loc = LocalisationClient(
            user_id=current_user.id,
            latitude=data.latitude,
            longitude=data.longitude,
            est_sos=True,
        )
        db.add(loc)

    # Notification pour le client
    notif_client = NotificationClient(
        user_id=current_user.id,
        titre="🚨 SOS déclenché",
        message="Votre alerte SOS a été transmise à nos équipes. "
                "Nous vous contactons dans les plus brefs délais.",
        type="danger",
        icone="fa-siren-on",
    )
    db.add(notif_client)

    db.commit()
    db.refresh(alerte)
    return alerte


@app.get("/client/sos/historique", response_model=List[SOSAlerteOut], tags=["Client – SOS"])
def historique_sos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Historique des SOS déclenchés par l'utilisateur connecté."""
    return (
        db.query(SOSAlerte)
        .filter(SOSAlerte.user_id == current_user.id)
        .order_by(SOSAlerte.created_at.desc())
        .all()
    )


# ── Notifications client ─────────────────────────────────────

@app.get("/client/notifications", response_model=List[NotificationOut], tags=["Client"])
def mes_notifications(
    non_lues_seulement: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupérer mes notifications."""
    q = db.query(NotificationClient).filter(
        NotificationClient.user_id == current_user.id
    )
    if non_lues_seulement:
        q = q.filter(NotificationClient.lue == False)
    return q.order_by(NotificationClient.created_at.desc()).limit(50).all()


@app.patch("/client/notifications/{notif_id}/lue", response_model=NotificationOut, tags=["Client"])
def marquer_notification_lue(
    notif_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marquer une notification comme lue."""
    notif = db.query(NotificationClient).filter(
        NotificationClient.id == notif_id,
        NotificationClient.user_id == current_user.id
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    notif.lue = True
    db.commit()
    db.refresh(notif)
    return notif


@app.post("/client/notifications/tout-lire", tags=["Client"])
def tout_marquer_lu(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marquer toutes les notifications comme lues."""
    db.query(NotificationClient).filter(
        NotificationClient.user_id == current_user.id,
        NotificationClient.lue == False
    ).update({"lue": True})
    db.commit()
    return {"message": "Toutes les notifications sont marquées comme lues"}


# ── Dashboard client ─────────────────────────────────────────

@app.get("/client/dashboard", tags=["Client"])
def dashboard_client(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Statistiques personnelles pour le dashboard client."""

    # Abonnement actif
    abo = db.query(Abonnement).filter(
        Abonnement.user_id == current_user.id,
        Abonnement.statut == "actif"
    ).order_by(Abonnement.date_souscription.desc()).first()

    # Nombre d'évacuations (interventions)
    nb_evacuations = db.query(Intervention).filter(
        Intervention.user_id == current_user.id
    ).count()

    # Profil médical
    profil = db.query(ProfilMedical).filter(
        ProfilMedical.user_id == current_user.id
    ).first()

    # Calcul de la complétude du profil médical (%)
    completude = 0
    if profil:
        champs = [
            profil.date_naissance, profil.sexe, profil.nationalite, profil.profession,
            profil.region, profil.quartier, profil.adresse_domicile,
            profil.lat_domicile, profil.lng_domicile,
            profil.groupe_sanguin, profil.taille_cm, profil.poids_kg,
            profil.maladies, profil.allergies, profil.medicaments,
            profil.antecedents_familiaux, profil.medecin_referent,
            profil.fumeur, profil.alcool, profil.activite_physique,
        ]
        remplis = sum(1 for c in champs if c is not None and str(c).strip() != "")
        completude = round(remplis / len(champs) * 100)

    # Notifications non lues
    nb_notifs_non_lues = db.query(NotificationClient).filter(
        NotificationClient.user_id == current_user.id,
        NotificationClient.lue == False
    ).count()

    # Contacts d'urgence
    nb_contacts = db.query(ContactUrgenceClient).filter(
        ContactUrgenceClient.user_id == current_user.id
    ).count()

    # Dernière localisation
    derniere_loc = db.query(LocalisationClient).filter(
        LocalisationClient.user_id == current_user.id
    ).order_by(LocalisationClient.envoyee_a.desc()).first()

    # Jours restants abonnement
    jours_restants = None
    if abo and abo.date_expiration:
        delta = abo.date_expiration - datetime.now(timezone.utc)
        jours_restants = max(0, delta.days)

    return {
        "utilisateur": {
            "id":         current_user.id,
            "prenom":     current_user.prenom,
            "nom":        current_user.nom,
            "email":      current_user.email,
            "telephone":  current_user.telephone,
            "quartier":   current_user.quartier,
        },
        "abonnement": {
            "plan":          abo.plan if abo else None,
            "statut":        abo.statut if abo else "aucun",
            "nb_personnes":  abo.nb_personnes if abo else 0,
            "jours_restants": jours_restants,
            "date_expiration": abo.date_expiration.isoformat() if abo and abo.date_expiration else None,
        },
        "profil_medical": {
            "completude_pct":  completude,
            "groupe_sanguin":  profil.groupe_sanguin if profil else None,
            "allergies":       profil.allergies if profil else None,
            "maladies":        profil.maladies if profil else None,
            "medicaments":     profil.medicaments if profil else None,
        },
        "activite": {
            "nb_evacuations":        nb_evacuations,
            "nb_contacts_urgence":   nb_contacts,
            "nb_notifs_non_lues":    nb_notifs_non_lues,
        },
        "derniere_localisation": {
            "latitude":  derniere_loc.latitude  if derniere_loc else None,
            "longitude": derniere_loc.longitude if derniere_loc else None,
            "envoyee_a": derniere_loc.envoyee_a.isoformat() if derniere_loc else None,
        } if derniere_loc else None,
    }


# ── Routes Admin supplémentaires pour SOS ───────────────────

@app.get("/admin/sos", response_model=List[SOSAlerteOut], tags=["Admin – SOS"])
def admin_liste_sos(
    statut: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Liste toutes les alertes SOS (admin). Filtrable par statut."""
    q = db.query(SOSAlerte)
    if statut:
        q = q.filter(SOSAlerte.statut == statut)
    return q.order_by(SOSAlerte.created_at.desc()).offset(skip).limit(limit).all()


@app.patch("/admin/sos/{sos_id}/statut", response_model=SOSAlerteOut, tags=["Admin – SOS"])
def admin_maj_sos(
    sos_id: str,
    statut: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour le statut d'un SOS (admin)."""
    sos = db.query(SOSAlerte).filter(SOSAlerte.id == sos_id).first()
    if not sos:
        raise HTTPException(status_code=404, detail="Alerte SOS introuvable")
    sos.statut = statut
    sos.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sos)
    return sos


@app.get("/admin/localisations", tags=["Admin"])
def admin_localisations_recentes(
    limit: int = 100,
    sos_seulement: bool = False,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Carte en temps réel : positions des clients (admin)."""
    q = db.query(LocalisationClient, User).join(
        User, LocalisationClient.user_id == User.id
    )
    if sos_seulement:
        q = q.filter(LocalisationClient.est_sos == True)
    rows = q.order_by(LocalisationClient.envoyee_a.desc()).limit(limit).all()
    return [
        {
            "user_id":    u.id,
            "nom_complet": f"{u.prenom} {u.nom}",
            "telephone":  u.telephone,
            "latitude":   loc.latitude,
            "longitude":  loc.longitude,
            "est_sos":    loc.est_sos,
            "envoyee_a":  loc.envoyee_a.isoformat(),
        }
        for loc, u in rows
    ]


@app.post("/admin/notifications/envoyer", tags=["Admin"])
def admin_envoyer_notification(
    user_id: str,
    titre: str,
    message: str,
    type_notif: str = "info",
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Envoyer une notification push à un utilisateur spécifique (admin)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    notif = NotificationClient(
        user_id=user_id,
        titre=titre,
        message=message,
        type=type_notif,
    )
    db.add(notif)
    db.commit()
    return {"message": f"Notification envoyée à {user.prenom} {user.nom}"}


# ── MODÈLES SQLALCHEMY (collez avec les autres classes Base) ──

class MediaStat(Base):
    """Statistiques d'engagement par média (likes, vues, partages)."""
    __tablename__ = "media_stats"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    media_id    = Column(String, nullable=False, index=True)   # ID de l'image ou vidéo
    media_type  = Column(String, nullable=False)               # "image" | "video"
    likes       = Column(Integer, default=0)
    views       = Column(Integer, default=0)
    shares      = Column(Integer, default=0)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MediaLike(Base):
    """Qui a liké quoi."""
    __tablename__ = "media_likes"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    media_id    = Column(String, nullable=False, index=True)
    media_type  = Column(String, nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="media_likes")


class MediaSave(Base):
    """Qui a sauvegardé quoi."""
    __tablename__ = "media_saves"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    media_id    = Column(String, nullable=False, index=True)
    media_type  = Column(String, nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="media_saves")


class MediaComment(Base):
    """Commentaires sur les médias."""
    __tablename__ = "media_comments"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    media_id    = Column(String, nullable=False, index=True)
    media_type  = Column(String, nullable=False)
    user_id     = Column(String, ForeignKey("users.id"), nullable=True)
    author_name = Column(String, nullable=False, default="Anonyme")
    text        = Column(Text, nullable=False)
    likes       = Column(Integer, default=0)
    parent_id   = Column(String, nullable=True)   # pour les réponses
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="media_comments")


# ── SCHÉMAS PYDANTIC (collez avec les autres schémas) ──────────

class MediaStatOut(BaseModel):
    media_id:   str
    media_type: str
    likes:      int
    views:      int
    shares:     int
    class Config:
        from_attributes = True


class CommentIn(BaseModel):
    text:        str
    author_name: Optional[str] = "Anonyme"
    parent_id:   Optional[str] = None


class CommentOut(BaseModel):
    id:          str
    media_id:    str
    media_type:  str
    user_id:     Optional[str]
    author_name: str
    text:        str
    likes:       int
    parent_id:   Optional[str]
    created_at:  datetime
    class Config:
        from_attributes = True


class FeedItemOut(BaseModel):
    """Élément du feed combiné images+vidéos."""
    id:           str
    titre:        str
    description:  Optional[str]
    categorie:    Optional[str]
    media_type:   str          # "image" | "video"
    url:          Optional[str]
    url_source:   Optional[str]  # pour les vidéos
    duree:        Optional[str]
    visibilite:   str
    created_at:   datetime
    likes:        int
    views:        int
    shares:       int
    comments:     int
    trending:     bool
    is_liked:     bool
    is_saved:     bool


# ── HELPER STATS ───────────────────────────────────────────────

def _get_or_create_stat(media_id: str, media_type: str, db: Session) -> MediaStat:
    """Récupère ou crée la ligne de stats pour un média."""
    stat = db.query(MediaStat).filter(
        MediaStat.media_id == media_id,
        MediaStat.media_type == media_type
    ).first()
    if not stat:
        stat = MediaStat(media_id=media_id, media_type=media_type)
        db.add(stat)
        db.commit()
        db.refresh(stat)
    return stat


def _build_feed_item(
    item,
    media_type: str,
    stat: Optional[MediaStat],
    db: Session,
    current_user: Optional[User] = None,
) -> dict:
    """Construit un dict FeedItemOut depuis un objet Image ou Video."""
    media_id = item.id
    nb_comments = db.query(MediaComment).filter(
        MediaComment.media_id == media_id,
        MediaComment.media_type == media_type,
    ).count()

    is_liked = False
    is_saved = False
    if current_user:
        is_liked = db.query(MediaLike).filter(
            MediaLike.media_id == media_id,
            MediaLike.user_id == current_user.id,
        ).first() is not None
        is_saved = db.query(MediaSave).filter(
            MediaSave.media_id == media_id,
            MediaSave.user_id == current_user.id,
        ).first() is not None

    likes  = stat.likes  if stat else 0
    views  = stat.views  if stat else 0
    shares = stat.shares if stat else 0
    trending = likes > 100 or views > 1000

    base = {
        "id":          item.id,
        "titre":       item.titre,
        "description": getattr(item, "description", None),
        "categorie":   getattr(item, "categorie", None),
        "media_type":  media_type,
        "url":         getattr(item, "url", None),
        "url_source":  getattr(item, "url_source", None),
        "duree":       getattr(item, "duree", None),
        "visibilite":  getattr(item, "visibilite", "Publier sur le site"),
        "created_at":  item.created_at,
        "likes":       likes,
        "views":       views,
        "shares":      shares,
        "comments":    nb_comments,
        "trending":    trending,
        "is_liked":    is_liked,
        "is_saved":    is_saved,
    }
    return base


# ══ ROUTES GALERIE /galerie ════════════════════════════════════

@app.get("/galerie/feed", tags=["Galerie"])
def feed_galerie(
    skip:       int = 0,
    limit:      int = 24,
    sort:       str = "recent",     # recent | likes | views | trending
    categorie:  Optional[str] = None,
    media_type: Optional[str] = None,  # image | video
    search:     Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Feed combiné images + vidéos, trié et filtré.
    Accessible sans authentification.
    """
    images = db.query(Image).filter(Image.visibilite != "Brouillon")
    videos = db.query(Video)

    # Filtre catégorie
    if categorie:
        images = images.filter(Image.categorie == categorie)
        videos = videos.filter(Video.categorie == categorie)

    # Filtre recherche
    if search:
        images = images.filter(Image.titre.ilike(f"%{search}%") | Image.description.ilike(f"%{search}%"))
        videos = videos.filter(Video.titre.ilike(f"%{search}%") | Video.description.ilike(f"%{search}%"))

    images_list = images.all() if media_type != "video" else []
    videos_list = videos.all() if media_type != "image" else []

    # Construire les items
    feed_items = []
    for img in images_list:
        stat = _get_or_create_stat(img.id, "image", db)
        feed_items.append(_build_feed_item(img, "image", stat, db, current_user))
    for vid in videos_list:
        stat = _get_or_create_stat(vid.id, "video", db)
        feed_items.append(_build_feed_item(vid, "video", stat, db, current_user))

    # Tri
    if sort == "likes":   feed_items.sort(key=lambda x: x["likes"],   reverse=True)
    elif sort == "views": feed_items.sort(key=lambda x: x["views"],   reverse=True)
    elif sort == "trending": feed_items.sort(key=lambda x: x["trending"], reverse=True)
    else:                 feed_items.sort(key=lambda x: x["created_at"], reverse=True)

    total = len(feed_items)
    return {
        "total":  total,
        "skip":   skip,
        "limit":  limit,
        "items":  feed_items[skip : skip + limit],
    }


@app.get("/galerie/trending", tags=["Galerie"])
def trending_galerie(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Les contenus les plus populaires (likes + vues)."""
    stats = db.query(MediaStat).order_by(
        (MediaStat.likes * 2 + MediaStat.views).desc()
    ).limit(limit).all()

    results = []
    for stat in stats:
        if stat.media_type == "image":
            item = db.query(Image).filter(Image.id == stat.media_id).first()
            if item:
                results.append(_build_feed_item(item, "image", stat, db, current_user))
        else:
            item = db.query(Video).filter(Video.id == stat.media_id).first()
            if item:
                results.append(_build_feed_item(item, "video", stat, db, current_user))
    return results


# ── VUES ──────────────────────────────────────────────────────

@app.post("/galerie/images/{img_id}/vue", tags=["Galerie"])
def vue_image(img_id: str, db: Session = Depends(get_db)):
    """Incrémenter le compteur de vues d'une image."""
    stat = _get_or_create_stat(img_id, "image", db)
    stat.views += 1
    stat.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"views": stat.views}


@app.post("/galerie/videos/{vid_id}/vue", tags=["Galerie"])
def vue_video(vid_id: str, db: Session = Depends(get_db)):
    """Incrémenter le compteur de vues d'une vidéo."""
    stat = _get_or_create_stat(vid_id, "video", db)
    stat.views += 1
    stat.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"views": stat.views}


# ── LIKES ─────────────────────────────────────────────────────

@app.post("/galerie/images/{img_id}/like", tags=["Galerie"])
def toggle_like_image(
    img_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Liker ou unliker une image. Retourne le nouveau total."""
    existing = db.query(MediaLike).filter(
        MediaLike.media_id == img_id,
        MediaLike.user_id  == current_user.id,
        MediaLike.media_type == "image",
    ).first()
    stat = _get_or_create_stat(img_id, "image", db)

    if existing:
        db.delete(existing)
        stat.likes = max(0, stat.likes - 1)
        liked = False
    else:
        db.add(MediaLike(user_id=current_user.id, media_id=img_id, media_type="image"))
        stat.likes += 1
        liked = True

    stat.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"liked": liked, "likes": stat.likes}


@app.post("/galerie/videos/{vid_id}/like", tags=["Galerie"])
def toggle_like_video(
    vid_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Liker ou unliker une vidéo."""
    existing = db.query(MediaLike).filter(
        MediaLike.media_id == vid_id,
        MediaLike.user_id  == current_user.id,
        MediaLike.media_type == "video",
    ).first()
    stat = _get_or_create_stat(vid_id, "video", db)

    if existing:
        db.delete(existing)
        stat.likes = max(0, stat.likes - 1)
        liked = False
    else:
        db.add(MediaLike(user_id=current_user.id, media_id=vid_id, media_type="video"))
        stat.likes += 1
        liked = True

    stat.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"liked": liked, "likes": stat.likes}


# ── PARTAGES ──────────────────────────────────────────────────

@app.post("/galerie/images/{img_id}/share", tags=["Galerie"])
def share_image(img_id: str, db: Session = Depends(get_db)):
    """Incrémenter le compteur de partages d'une image."""
    stat = _get_or_create_stat(img_id, "image", db)
    stat.shares += 1
    stat.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"shares": stat.shares}


@app.post("/galerie/videos/{vid_id}/share", tags=["Galerie"])
def share_video(vid_id: str, db: Session = Depends(get_db)):
    """Incrémenter le compteur de partages d'une vidéo."""
    stat = _get_or_create_stat(vid_id, "video", db)
    stat.shares += 1
    stat.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"shares": stat.shares}


# ── SAUVEGARDES ───────────────────────────────────────────────

@app.post("/galerie/images/{img_id}/save", tags=["Galerie"])
def toggle_save_image(
    img_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sauvegarder / retirer une image des favoris."""
    existing = db.query(MediaSave).filter(
        MediaSave.media_id == img_id,
        MediaSave.user_id  == current_user.id,
        MediaSave.media_type == "image",
    ).first()
    if existing:
        db.delete(existing)
        saved = False
    else:
        db.add(MediaSave(user_id=current_user.id, media_id=img_id, media_type="image"))
        saved = True
    db.commit()
    return {"saved": saved}


@app.post("/galerie/videos/{vid_id}/save", tags=["Galerie"])
def toggle_save_video(
    vid_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sauvegarder / retirer une vidéo des favoris."""
    existing = db.query(MediaSave).filter(
        MediaSave.media_id == vid_id,
        MediaSave.user_id  == current_user.id,
        MediaSave.media_type == "video",
    ).first()
    if existing:
        db.delete(existing)
        saved = False
    else:
        db.add(MediaSave(user_id=current_user.id, media_id=vid_id, media_type="video"))
        saved = True
    db.commit()
    return {"saved": saved}


@app.get("/galerie/saved", tags=["Galerie"])
def mes_sauvegardes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retourne tous les médias sauvegardés par l'utilisateur connecté."""
    saves = db.query(MediaSave).filter(MediaSave.user_id == current_user.id).all()
    results = []
    for s in saves:
        if s.media_type == "image":
            item = db.query(Image).filter(Image.id == s.media_id).first()
            if item:
                stat = _get_or_create_stat(item.id, "image", db)
                results.append(_build_feed_item(item, "image", stat, db, current_user))
        else:
            item = db.query(Video).filter(Video.id == s.media_id).first()
            if item:
                stat = _get_or_create_stat(item.id, "video", db)
                results.append(_build_feed_item(item, "video", stat, db, current_user))
    return results


# ── COMMENTAIRES IMAGES ───────────────────────────────────────

@app.get("/galerie/images/{img_id}/comments", response_model=List[CommentOut], tags=["Galerie"])
def get_comments_image(img_id: str, db: Session = Depends(get_db)):
    """Récupérer tous les commentaires d'une image."""
    return (
        db.query(MediaComment)
        .filter(MediaComment.media_id == img_id, MediaComment.media_type == "image")
        .order_by(MediaComment.created_at.desc())
        .all()
    )


@app.post("/galerie/images/{img_id}/comments", response_model=CommentOut, status_code=201, tags=["Galerie"])
def add_comment_image(
    img_id: str,
    data: CommentIn,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Ajouter un commentaire sur une image."""
    comment = MediaComment(
        media_id=img_id,
        media_type="image",
        user_id=current_user.id if current_user else None,
        author_name=current_user.prenom if current_user else (data.author_name or "Anonyme"),
        text=data.text,
        parent_id=data.parent_id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@app.delete("/galerie/images/comments/{comment_id}", status_code=204, tags=["Galerie"])
def delete_comment_image(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprimer un commentaire (auteur ou admin)."""
    comment = db.query(MediaComment).filter(MediaComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire introuvable")
    if comment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès refusé")
    db.delete(comment)
    db.commit()


@app.post("/galerie/images/comments/{comment_id}/like", tags=["Galerie"])
def like_comment(comment_id: str, db: Session = Depends(get_db)):
    """Liker un commentaire."""
    comment = db.query(MediaComment).filter(MediaComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire introuvable")
    comment.likes += 1
    db.commit()
    return {"likes": comment.likes}


# ── COMMENTAIRES VIDÉOS ───────────────────────────────────────

@app.get("/galerie/videos/{vid_id}/comments", response_model=List[CommentOut], tags=["Galerie"])
def get_comments_video(vid_id: str, db: Session = Depends(get_db)):
    """Récupérer tous les commentaires d'une vidéo."""
    return (
        db.query(MediaComment)
        .filter(MediaComment.media_id == vid_id, MediaComment.media_type == "video")
        .order_by(MediaComment.created_at.desc())
        .all()
    )


@app.post("/galerie/videos/{vid_id}/comments", response_model=CommentOut, status_code=201, tags=["Galerie"])
def add_comment_video(
    vid_id: str,
    data: CommentIn,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Ajouter un commentaire sur une vidéo."""
    comment = MediaComment(
        media_id=vid_id,
        media_type="video",
        user_id=current_user.id if current_user else None,
        author_name=current_user.prenom if current_user else (data.author_name or "Anonyme"),
        text=data.text,
        parent_id=data.parent_id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@app.delete("/galerie/videos/comments/{comment_id}", status_code=204, tags=["Galerie"])
def delete_comment_video(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprimer un commentaire (auteur ou admin)."""
    comment = db.query(MediaComment).filter(MediaComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire introuvable")
    if comment.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès refusé")
    db.delete(comment)
    db.commit()


# ── STATS GLOBALES GALERIE (admin) ────────────────────────────

@app.get("/galerie/stats", tags=["Galerie"])
def stats_galerie(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Statistiques globales de la galerie (admin uniquement)."""
    total_images = db.query(Image).count()
    total_videos = db.query(Video).count()

    total_likes  = db.query(func.sum(MediaStat.likes)).scalar()  or 0
    total_views  = db.query(func.sum(MediaStat.views)).scalar()  or 0
    total_shares = db.query(func.sum(MediaStat.shares)).scalar() or 0
    total_comments = db.query(MediaComment).count()

    # Top 5 images likées
    top_images = (
        db.query(MediaStat)
        .filter(MediaStat.media_type == "image")
        .order_by(MediaStat.likes.desc())
        .limit(5)
        .all()
    )
    # Top 5 vidéos vues
    top_videos = (
        db.query(MediaStat)
        .filter(MediaStat.media_type == "video")
        .order_by(MediaStat.views.desc())
        .limit(5)
        .all()
    )

    return {
        "totaux": {
            "images":   total_images,
            "videos":   total_videos,
            "medias":   total_images + total_videos,
            "likes":    total_likes,
            "views":    total_views,
            "shares":   total_shares,
            "comments": total_comments,
        },
        "top_images_likes": [
            {"media_id": s.media_id, "likes": s.likes, "views": s.views}
            for s in top_images
        ],
        "top_videos_vues": [
            {"media_id": s.media_id, "views": s.views, "likes": s.likes}
            for s in top_videos
        ],
    }


# ── STATS D'UN MÉDIA SPÉCIFIQUE ───────────────────────────────

@app.get("/galerie/images/{img_id}/stats", tags=["Galerie"])
def stats_image(img_id: str, db: Session = Depends(get_db)):
    """Stats (likes, vues, partages, commentaires) d'une image."""
    stat = db.query(MediaStat).filter(
        MediaStat.media_id == img_id, MediaStat.media_type == "image"
    ).first()
    nb_comments = db.query(MediaComment).filter(
        MediaComment.media_id == img_id, MediaComment.media_type == "image"
    ).count()
    return {
        "media_id": img_id,
        "likes":    stat.likes    if stat else 0,
        "views":    stat.views    if stat else 0,
        "shares":   stat.shares   if stat else 0,
        "comments": nb_comments,
    }


@app.get("/galerie/videos/{vid_id}/stats", tags=["Galerie"])
def stats_video(vid_id: str, db: Session = Depends(get_db)):
    """Stats (likes, vues, partages, commentaires) d'une vidéo."""
    stat = db.query(MediaStat).filter(
        MediaStat.media_id == vid_id, MediaStat.media_type == "video"
    ).first()
    nb_comments = db.query(MediaComment).filter(
        MediaComment.media_id == vid_id, MediaComment.media_type == "video"
    ).count()
    return {
        "media_id": vid_id,
        "likes":    stat.likes    if stat else 0,
        "views":    stat.views    if stat else 0,
        "shares":   stat.shares   if stat else 0,
        "comments": nb_comments,
    }


import secrets
import hashlib


# ─── CONFIG SUPPLÉMENTAIRE ───────────────────────────────────

# Code secret requis pour créer un compte administrateur.
# Changez cette valeur et stockez-la dans une variable d'environnement.
ADMIN_ACCESS_CODE = os.getenv("ADMIN_ACCESS_CODE", "ABALO-ADMIN-2026")

# Durée de validité des tokens de réinitialisation (en minutes)
RESET_TOKEN_EXPIRE_MINUTES = 30

# Stockage en mémoire des tokens de réinitialisation
# En production, utilisez Redis ou une table SQL dédiée.
_reset_tokens: dict[str, dict] = {}  # {token_hash: {user_id, expires_at}}

# Blacklist des tokens JWT révoqués (logout)
# En production, utilisez Redis avec TTL.
_token_blacklist: set[str] = set()


# ─── MODÈLE SQLALCHEMY SUPPLÉMENTAIRE ───────────────────────
# Table pour conserver l'historique des connexions admin

class AdminLoginHistory(Base):
    __tablename__ = "admin_login_history"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    ip_address  = Column(String, nullable=True)
    user_agent  = Column(String, nullable=True)
    success     = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="login_history")


# Créer la table si elle n'existe pas encore
# (déjà géré par Base.metadata.create_all dans votre main.py)


# ─── SCHÉMAS PYDANTIC SUPPLÉMENTAIRES ───────────────────────

class AdminRegisterIn(BaseModel):
    """Inscription d'un administrateur avec code d'accès."""
    prenom:       str
    nom:          str
    email:        EmailStr
    telephone:    Optional[str]  = None
    password:     str
    access_code:  str            # Code secret fourni par le super-admin
    role:         Optional[str]  = None  # super_admin | admin | gestionnaire_rh | ...


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token:        str
    new_password: str


class AdminOut(BaseModel):
    """Vue allégée d'un compte admin pour la liste."""
    id:         str
    prenom:     str
    nom:        str
    email:      str
    telephone:  Optional[str]
    is_active:  bool
    is_admin:   bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenVerifyOut(BaseModel):
    valid:    bool
    user_id:  Optional[str]  = None
    prenom:   Optional[str]  = None
    nom:      Optional[str]  = None
    email:    Optional[str]  = None
    is_admin: Optional[bool] = None
    expires:  Optional[str]  = None


# ─── HELPER : Dépendance pour vérifier blacklist ─────────────

def get_valid_token(
    token: str = Depends(oauth2_scheme),
    db:    Session = Depends(get_db),
) -> User:
    """Comme get_current_user mais vérifie aussi la blacklist."""
    if _hash_token(token) in _token_blacklist:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token révoqué (déconnexion effectuée)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_current_user.__wrapped__(token, db) if hasattr(get_current_user, '__wrapped__') else get_current_user(token, db)


def _hash_token(token: str) -> str:
    """Hash SHA-256 du token pour la blacklist (ne stocke jamais le token brut)."""
    return hashlib.sha256(token.encode()).hexdigest()


# ─── ROUTES ──────────────────────────────────────────────────
# ── 1. INSCRIPTION ADMIN AVEC CODE D'ACCÈS ───────────────────

@app.post(
    "/auth/register-admin",
    response_model=LoginOut,
    status_code=201,
    tags=["Auth – Admin"],
    summary="Créer un compte administrateur (code requis)",
)
def register_admin(
    data: AdminRegisterIn,
    db:   Session = Depends(get_db),
):
    """
    Crée un compte administrateur.
    Nécessite un code d'accès secret (`access_code`) fourni par le super-admin.
    Le compte créé a `is_admin = True` automatiquement.
    """
    # ── Vérification du code d'accès ──
    if data.access_code.strip() != ADMIN_ACCESS_CODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Code d'accès administrateur invalide. Contactez le super-administrateur.",
        )

    # ── Email unique ──
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cette adresse email est déjà associée à un compte.",
        )

    # ── Validation mot de passe ──
    if len(data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le mot de passe doit contenir au moins 8 caractères.",
        )

    # ── Création du compte ──
    user = User(
        prenom=data.prenom.strip(),
        nom=data.nom.strip(),
        email=data.email,
        telephone=data.telephone,
        quartier=data.role,          # On stocke temporairement le rôle dans quartier
        hashed_password=hash_password(data.password),
        is_admin=True,
        is_active=True,
    )
    db.add(user)


    db.add(user)
    db.commit()
    db.refresh(user)             # ← maintenant user.id existe

    db.add(AdminLoginHistory(    # ← on log après
        user_id=user.id,
        success=True,
    ))
    db.commit()

    # ── Génération du token ──
    token = create_access_token(
        {"sub": user.id},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return LoginOut(
        access_token=token,
        user_id=user.id,
        prenom=user.prenom,
        nom=user.nom,
        email=user.email,
        is_admin=user.is_admin,
    )


# ── 2. VÉRIFICATION DISPONIBILITÉ EMAIL ──────────────────────

@app.get(
    "/auth/check-email",
    tags=["Auth – Admin"],
    summary="Vérifier si un email est disponible",
)
def check_email_availability(
    email: str = Query(..., description="L'adresse email à vérifier"),
    db:    Session = Depends(get_db),
):
    """
    Retourne `{"available": true}` si l'email n'est pas encore utilisé.
    Utilisé par le formulaire d'inscription pour validation en temps réel.
    """
    exists = db.query(User).filter(User.email == email.lower().strip()).first()
    return {"email": email, "available": exists is None}


# ── 3. MOT DE PASSE OUBLIÉ ───────────────────────────────────

@app.post(
    "/auth/forgot-password",
    tags=["Auth – Admin"],
    summary="Demande de réinitialisation de mot de passe",
)
def forgot_password(
    data: ForgotPasswordIn,
    db:   Session = Depends(get_db),
):
    """
    Génère un token de réinitialisation (valide 30 min).
    En production : envoyez ce token par email (ex. via SendGrid, Mailgun).
    Retourne toujours 200 même si l'email n'existe pas (sécurité anti-enumération).
    """
    user = db.query(User).filter(User.email == data.email).first()

    if user and user.is_admin:
        # Générer un token sécurisé
        raw_token = secrets.token_urlsafe(48)
        token_hash = _hash_token(raw_token)

        _reset_tokens[token_hash] = {
            "user_id":    user.id,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
        }

        print(f"\n[DEV] Token de réinitialisation pour {user.email}: {raw_token}\n")

    # Toujours retourner 200 (anti-enumération)
    return {
        "message": "Si un compte administrateur correspond à cet email, "
                   "un lien de réinitialisation a été envoyé.",
    }


# ── 4. RÉINITIALISATION DU MOT DE PASSE ──────────────────────

@app.post(
    "/auth/reset-password",
    tags=["Auth – Admin"],
    summary="Réinitialiser le mot de passe avec un token",
)
def reset_password(
    data: ResetPasswordIn,
    db:   Session = Depends(get_db),
):
    """
    Réinitialise le mot de passe en échangeant le token reçu par email.
    Le token est invalidé après utilisation (usage unique).
    """
    token_hash = _hash_token(data.token)
    record = _reset_tokens.get(token_hash)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token invalide ou déjà utilisé.",
        )

    if datetime.now(timezone.utc) > record["expires_at"]:
        del _reset_tokens[token_hash]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token expiré. Veuillez refaire une demande de réinitialisation.",
        )

    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le nouveau mot de passe doit contenir au moins 8 caractères.",
        )

    user = db.query(User).filter(User.id == record["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    user.hashed_password = hash_password(data.new_password)
    db.commit()

    # Invalider le token après usage
    del _reset_tokens[token_hash]

    return {"message": "Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."}


# ── 5. VÉRIFICATION DU TOKEN JWT ─────────────────────────────

@app.get(
    "/auth/verify-token",
    response_model=TokenVerifyOut,
    tags=["Auth – Admin"],
    summary="Vérifier si le token JWT est valide",
)
def verify_token(
    token: str = Depends(oauth2_scheme),
    db:    Session = Depends(get_db),
):
    """
    Valide le token JWT et retourne les infos de l'utilisateur.
    Utilisé par le dashboard frontend au chargement pour vérifier la session.
    Retourne `{"valid": false}` si le token est invalide ou expiré.
    """
    # Vérifier blacklist
    if _hash_token(token) in _token_blacklist:
        return TokenVerifyOut(valid=False)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        exp = payload.get("exp")
        if not user_id:
            return TokenVerifyOut(valid=False)

        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            return TokenVerifyOut(valid=False)

        expires_at = None
        if exp:
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()

        return TokenVerifyOut(
            valid=True,
            user_id=user.id,
            prenom=user.prenom,
            nom=user.nom,
            email=user.email,
            is_admin=user.is_admin,
            expires=expires_at,
        )

    except JWTError:
        return TokenVerifyOut(valid=False)


# ── 6. DÉCONNEXION (LOGOUT + BLACKLIST) ──────────────────────

@app.post(
    "/auth/logout",
    tags=["Auth – Admin"],
    summary="Déconnexion – invalider le token",
)
def logout(
    token:        str     = Depends(oauth2_scheme),
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Invalide le token JWT de l'utilisateur (blacklist côté serveur).
    Le client doit aussi supprimer le token de localStorage/sessionStorage.
    """
    # Ajouter à la blacklist
    _token_blacklist.add(_hash_token(token))

    # Log de déconnexion
    db.add(AdminLoginHistory(
        user_id=current_user.id,
        success=True,
    ))
    db.commit()

    return {
        "message": f"Au revoir {current_user.prenom} ! Vous avez été déconnecté avec succès.",
        "user": f"{current_user.prenom} {current_user.nom}",
    }


# ── 7. LISTE DES ADMINISTRATEURS (super-admin) ───────────────

@app.get(
    "/auth/admins",
    response_model=List[AdminOut],
    tags=["Auth – Admin"],
    summary="Lister tous les comptes administrateurs",
)
def list_admins(
    search:       Optional[str] = None,
    is_active:    Optional[bool] = None,
    admin:        User    = Depends(get_admin_user),
    db:           Session = Depends(get_db),
):
    """
    Liste tous les comptes avec `is_admin = True`.
    Filtrable par nom/email et statut actif.
    Accessible à tout admin.
    """
    q = db.query(User).filter(User.is_admin == True)

    if search:
        q = q.filter(
            User.nom.ilike(f"%{search}%")
            | User.prenom.ilike(f"%{search}%")
            | User.email.ilike(f"%{search}%")
        )

    if is_active is not None:
        q = q.filter(User.is_active == is_active)

    return q.order_by(User.created_at.desc()).all()


# ── 8. ACTIVER / DÉSACTIVER UN COMPTE ADMIN ──────────────────

@app.patch(
    "/auth/admins/{user_id}/toggle",
    response_model=AdminOut,
    tags=["Auth – Admin"],
    summary="Activer ou désactiver un compte administrateur",
)
def toggle_admin_account(
    user_id: str,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """
    Bascule l'état actif/inactif d'un compte administrateur.
    Un admin ne peut pas se désactiver lui-même.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas désactiver votre propre compte.",
        )

    user = db.query(User).filter(User.id == user_id, User.is_admin == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="Administrateur introuvable.")

    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)

    action = "activé" if user.is_active else "désactivé"
    print(f"[ADMIN] Compte de {user.prenom} {user.nom} ({user.email}) {action} par {admin.email}")

    return user


# ── 9. HISTORIQUE DES CONNEXIONS (admin) ─────────────────────

@app.get(
    "/auth/login-history",
    tags=["Auth – Admin"],
    summary="Historique des connexions administrateurs",
)
def login_history(
    limit:  int     = 50,
    admin:  User    = Depends(get_admin_user),
    db:     Session = Depends(get_db),
):
    """Retourne les 50 dernières connexions admin (succès et échecs)."""
    rows = (
        db.query(AdminLoginHistory, User)
        .join(User, AdminLoginHistory.user_id == User.id)
        .order_by(AdminLoginHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":         h.id,
            "user_id":    h.user_id,
            "nom_complet": f"{u.prenom} {u.nom}",
            "email":      u.email,
            "success":    h.success,
            "ip_address": h.ip_address,
            "created_at": h.created_at.isoformat(),
        }
        for h, u in rows
    ]




# ── 10. MODIFIER MON PROFIL ADMIN ────────────────────────────

class AdminUpdateProfileIn(BaseModel):
    prenom:     Optional[str] = None
    nom:        Optional[str] = None
    telephone:  Optional[str] = None


@app.patch(
    "/auth/me/profile",
    response_model=AdminOut,
    tags=["Auth – Admin"],
    summary="Modifier son propre profil administrateur",
)
def update_admin_profile(
    data:         AdminUpdateProfileIn,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Met à jour le profil de l'admin connecté (prénom, nom, téléphone)."""
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


# ── 11. CHANGER MON MOT DE PASSE (admin connecté) ────────────

class AdminChangePasswordIn(BaseModel):
    ancien_mot_de_passe:  str
    nouveau_mot_de_passe: str


@app.post(
    "/auth/me/change-password",
    tags=["Auth – Admin"],
    summary="Changer son mot de passe (admin connecté)",
)
def admin_change_password(
    data:         AdminChangePasswordIn,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Permet à un admin connecté de changer son mot de passe.
    L'ancien mot de passe est vérifié avant la mise à jour.
    """
    if not verify_password(data.ancien_mot_de_passe, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="L'ancien mot de passe est incorrect.",
        )

    if len(data.nouveau_mot_de_passe) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le nouveau mot de passe doit contenir au moins 8 caractères.",
        )

    current_user.hashed_password = hash_password(data.nouveau_mot_de_passe)
    db.commit()

    return {"message": "Mot de passe mis à jour avec succès."}


# ── 12. ROUTE INFO : VÉRIFIER LE CODE D'ACCÈS (dev) ─────────

@app.post(
    "/auth/verify-access-code",
    tags=["Auth – Admin"],
    summary="Vérifier si un code d'accès admin est valide (step 2)",
)
def verify_access_code(
    code: str = Query(..., description="Le code d'accès à vérifier"),
):
    """
    Vérifie si le code d'accès est correct sans créer de compte.
    Utilisé par le formulaire multi-step pour valider dès l'étape 2.
    """
    valid = code.strip() == ADMIN_ACCESS_CODE
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Code d'accès invalide.",
        )
    return {"valid": True, "message": "Code d'accès valide."}




# ─── CONFIG upload ───────────────────────────────────────────
import shutil
from fastapi import File, UploadFile, Form
from fastapi.staticfiles import StaticFiles

UPLOAD_DIR = "uploads"
BASE_URL = os.getenv("BASE_URL", "http://localhost:8026")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ─── ENDPOINT UPLOAD IMAGE ───────────────────────────────────
@app.post("/media/images/upload", response_model=ImageOut, status_code=201, tags=["Media"])
async def upload_image_fichier(
    fichier:   UploadFile = File(...),
    titre:     str        = Form(default=""),
    categorie: str        = Form(default="Autre"),
    visibilite:str        = Form(default="Publier sur le site"),
    description: str      = Form(default=""),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    # Vérification du type MIME
    types_autorises = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"]
    if fichier.content_type not in types_autorises:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {fichier.content_type}. Accepté : JPG, PNG, WEBP, GIF"
        )

    # Vérification taille (5 MB max)
    contenu = await fichier.read()
    if len(contenu) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 5 MB)")

    # Nom unique pour éviter les collisions
    extension = fichier.filename.rsplit(".", 1)[-1].lower() if "." in fichier.filename else "jpg"
    nom_fichier = f"{uuid.uuid4()}.{extension}"
    chemin_complet = os.path.join(UPLOAD_DIR, nom_fichier)

    
    with open(chemin_complet, "wb") as f:
        f.write(contenu)


    url_publique = f"{BASE_URL}/uploads/{nom_fichier}"


    img = Image(
        titre=titre or fichier.filename,
        categorie=categorie or "Autre",
        url=url_publique,
        description=description or None,
        visibilite=visibilite or "Publier sur le site",
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return img

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")





from fastapi import File, UploadFile, Form

@app.post("/media/videos/upload", response_model=VideoOut, status_code=201, tags=["Media"])
async def upload_video_fichier(
    fichier:    UploadFile = File(...),
    titre:      str        = Form(default=""),
    categorie:  str        = Form(default="Intervention"),
    duree:      str        = Form(default=""),
    description:str        = Form(default=""),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    types_autorises = ["video/mp4", "video/quicktime", "video/webm", "video/avi"]
    if fichier.content_type not in types_autorises:
        raise HTTPException(status_code=400, detail="Format non supporté. Accepté : MP4, MOV, WEBM")

    contenu = await fichier.read()
    if len(contenu) > 200 * 1024 * 1024:  # 200 MB max
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 200 MB)")

    extension = fichier.filename.rsplit(".", 1)[-1].lower()
    nom_fichier = f"{uuid.uuid4()}.{extension}"
    chemin_complet = os.path.join(UPLOAD_DIR, nom_fichier)

    with open(chemin_complet, "wb") as f:
        f.write(contenu)

    url_publique = f"{BASE_URL}/uploads/{nom_fichier}"

    vid = Video(
        titre=titre or fichier.filename,
        categorie=categorie,
        url_source=url_publique,
        type_source="upload",
        duree=duree or None,
        description=description or None,
    )
    db.add(vid)
    db.commit()
    db.refresh(vid)
    return vid









# ══════════════════════════════════════════════════════════════════════
# SECOURS ABALO – SOS IA PRO
# Copiez ce bloc dans main.py AVANT la ligne Base.metadata.create_all
# ══════════════════════════════════════════════════════════════════════

# ── MODÈLES SQLAlchemy ────────────────────────────────────────────────

class SOSIAProConfig(Base):
    """Configuration SOS IA Pro par utilisateur (une ligne par user)."""
    __tablename__ = "sos_ia_pro_configs"

    id               = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id          = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    interval_minutes = Column(Integer, default=20)
    is_active        = Column(Boolean, default=False)
    next_check_at    = Column(DateTime, nullable=True)
    last_check_at    = Column(DateTime, nullable=True)
    current_check_id = Column(String, nullable=True)  # ID du check en cours non répondu
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="sos_ia_pro_config")


class SOSIAProCheck(Base):
    """Enregistrement de chaque vérification SOS IA Pro."""
    __tablename__ = "sos_ia_pro_checks"

    id                = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id           = Column(String, ForeignKey("users.id"), nullable=False)
    sent_at           = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    responded_at      = Column(DateTime, nullable=True)
    response_type     = Column(String, nullable=True)  # ok | not_ok_self | emergency
    reminder_count    = Column(Integer, default=0)      # 0=premier envoi, 1=rappel, 2=contacts alertés
    contacts_notified = Column(Boolean, default=False)
    sos_triggered     = Column(Boolean, default=False)
    sos_alerte_id     = Column(String, nullable=True)   # ID du SOSAlerte créé si déclenché
    created_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="sos_ia_pro_checks")


# ── SCHÉMAS Pydantic ──────────────────────────────────────────────────

class SOSIAProActiverIn(BaseModel):
    interval_minutes: int = 20  # entre 5 et 120 minutes


class SOSIAProConfigOut(BaseModel):
    id:               str
    user_id:          str
    interval_minutes: int
    is_active:        bool
    next_check_at:    Optional[datetime]
    last_check_at:    Optional[datetime]
    current_check_id: Optional[str]
    created_at:       datetime
    updated_at:       datetime
    class Config:
        from_attributes = True


class SOSIAProPendingOut(BaseModel):
    has_pending:    bool
    check_id:       Optional[str]   = None
    # action : new_check | remind | notify_contacts | auto_sos | waiting
    action:         Optional[str]   = None
    reminder_count: int             = 0
    sent_at:        Optional[datetime] = None
    sos_data:       Optional[dict]  = None  # rempli lors d'un auto_sos


class SOSIAProRepondreIn(BaseModel):
    check_id:  str
    response:  str           # ok | not_ok_self | emergency
    latitude:  Optional[float] = None
    longitude: Optional[float] = None


class SOSIAProRepondreOut(BaseModel):
    success:       bool
    response:      str
    next_check_at: Optional[datetime] = None
    message:       str
    sos_alerte:    Optional[dict] = None  # rempli si emergency


# ── HELPER interne ────────────────────────────────────────────────────

def _sos_ia_get_or_create_config(user_id: str, db) -> "SOSIAProConfig":
    cfg = db.query(SOSIAProConfig).filter(
        SOSIAProConfig.user_id == user_id
    ).first()
    if not cfg:
        cfg = SOSIAProConfig(user_id=user_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _sos_ia_build_alerte(current_user, db, latitude=None, longitude=None, note=""):
    """Crée un SOSAlerte et le sauvegarde en base."""
    profil = db.query(ProfilMedical).filter(
        ProfilMedical.user_id == current_user.id
    ).first()
    if latitude is None or longitude is None:
        derniere_loc = db.query(LocalisationClient).filter(
            LocalisationClient.user_id == current_user.id
        ).order_by(LocalisationClient.envoyee_a.desc()).first()
        if derniere_loc:
            latitude  = derniere_loc.latitude
            longitude = derniere_loc.longitude
    alerte = SOSAlerte(
        user_id          = current_user.id,
        nom_complet      = f"{current_user.prenom} {current_user.nom}",
        telephone        = current_user.telephone,
        groupe_sanguin   = profil.groupe_sanguin   if profil else None,
        allergies        = profil.allergies        if profil else None,
        maladies         = profil.maladies         if profil else None,
        medicaments      = profil.medicaments      if profil else None,
        medecin_referent = profil.medecin_referent if profil else None,
        latitude         = latitude,
        longitude        = longitude,
        statut           = "actif",
        note_urgence     = note,
    )
    db.add(alerte)
    db.flush()  # pour récupérer l'ID avant commit
    return alerte


# ── ROUTES ────────────────────────────────────────────────────────────

@app.post(
    "/client/sos-ia-pro/activer",
    response_model=SOSIAProConfigOut,
    status_code=201,
    tags=["SOS IA Pro"],
)
def activer_sos_ia_pro(
    data: SOSIAProActiverIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activer le SOS IA Pro avec un intervalle de vérification en minutes."""
    if not (5 <= data.interval_minutes <= 120):
        raise HTTPException(status_code=400, detail="Intervalle entre 5 et 120 minutes.")
    now = datetime.now(timezone.utc)
    cfg = _sos_ia_get_or_create_config(current_user.id, db)
    cfg.interval_minutes = data.interval_minutes
    cfg.is_active        = True
    cfg.next_check_at    = now + timedelta(minutes=data.interval_minutes)
    cfg.current_check_id = None
    cfg.updated_at       = now
    db.commit()
    db.refresh(cfg)
    return cfg


@app.get(
    "/client/sos-ia-pro/config",
    response_model=SOSIAProConfigOut,
    tags=["SOS IA Pro"],
)
def get_sos_ia_pro_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupérer la configuration SOS IA Pro de l'utilisateur connecté."""
    cfg = db.query(SOSIAProConfig).filter(
        SOSIAProConfig.user_id == current_user.id
    ).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="SOS IA Pro non encore configuré.")
    return cfg


@app.delete(
    "/client/sos-ia-pro/desactiver",
    tags=["SOS IA Pro"],
)
def desactiver_sos_ia_pro(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Désactiver le SOS IA Pro (arrêter les vérifications automatiques)."""
    cfg = db.query(SOSIAProConfig).filter(
        SOSIAProConfig.user_id == current_user.id
    ).first()
    if cfg:
        cfg.is_active        = False
        cfg.current_check_id = None
        cfg.next_check_at    = None
        cfg.updated_at       = datetime.now(timezone.utc)
        db.commit()
    return {"message": "SOS IA Pro désactivé avec succès."}


@app.get(
    "/client/sos-ia-pro/pending",
    response_model=SOSIAProPendingOut,
    tags=["SOS IA Pro"],
)
def check_sos_ia_pro_pending(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Endpoint de polling (appelé toutes les 30 s côté client).
    Gère toute la machine à états :
      T+0   → new_check    (affiche la notification)
      T+60s → remind       (rappel si pas de réponse)
      T+2m  → notify_contacts (crée SOSAlerte 'attention', alerte admin)
      T+3m  → auto_sos    (SOS automatique complet)
    """
    cfg = db.query(SOSIAProConfig).filter(
        SOSIAProConfig.user_id == current_user.id,
        SOSIAProConfig.is_active == True,
    ).first()
    if not cfg:
        return SOSIAProPendingOut(has_pending=False)

    now = datetime.now(timezone.utc)

    # ─── Cas 1 : check en cours non répondu ──────────────────────────
    if cfg.current_check_id:
        check = db.query(SOSIAProCheck).filter(
            SOSIAProCheck.id == cfg.current_check_id
        ).first()

        if check and not check.responded_at:
            sent_at = check.sent_at
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=timezone.utc)
            elapsed_s = (now - sent_at).total_seconds()

            # T+60s : premier rappel
            if elapsed_s >= 60 and check.reminder_count == 0:
                check.reminder_count = 1
                db.commit()
                return SOSIAProPendingOut(
                    has_pending    = True,
                    check_id       = check.id,
                    action         = "remind",
                    reminder_count = 1,
                    sent_at        = check.sent_at,
                )

            # T+120s : alerter les contacts + créer SOSAlerte d'attention
            if elapsed_s >= 120 and check.reminder_count == 1 and not check.contacts_notified:
                check.reminder_count    = 2
                check.contacts_notified = True

                # Créer une alerte admin visible (statut "attention_requise")
                alerte_attn = _sos_ia_build_alerte(
                    current_user, db,
                    note="🤖 SOS IA Pro – Aucune réponse après 2 minutes. Contacts alertés."
                )
                alerte_attn.statut = "attention_requise"
                # Notification pour l'admin via NotificationClient (réutilise le modèle existant)
                notif_admin = NotificationClient(
                    user_id = current_user.id,
                    titre   = "⚠️ SOS IA Pro – Pas de réponse",
                    message = (
                        f"{current_user.prenom} {current_user.nom} ne répond pas "
                        "aux vérifications automatiques depuis 2 minutes. "
                        "Contacts d'urgence notifiés."
                    ),
                    type  = "warning",
                    icone = "fa-brain",
                )
                db.add(notif_admin)
                db.commit()

                return SOSIAProPendingOut(
                    has_pending    = True,
                    check_id       = check.id,
                    action         = "notify_contacts",
                    reminder_count = 2,
                    sent_at        = check.sent_at,
                )

            # T+180s : SOS automatique complet
            if elapsed_s >= 180 and check.reminder_count >= 2 and not check.sos_triggered:
                check.sos_triggered = True
                alerte = _sos_ia_build_alerte(
                    current_user, db,
                    note=(
                        "🤖 SOS IA Pro – Déclenchement automatique. "
                        "Aucune réponse détectée après 3 minutes."
                    )
                )
                check.sos_alerte_id = alerte.id

                # Désactiver le SOS IA Pro après déclenchement automatique
                cfg.is_active        = False
                cfg.current_check_id = None
                db.commit()
                db.refresh(alerte)

                sos_data = {
                    "id":              alerte.id,
                    "nom_complet":     alerte.nom_complet,
                    "telephone":       alerte.telephone,
                    "groupe_sanguin":  alerte.groupe_sanguin,
                    "allergies":       alerte.allergies,
                    "maladies":        alerte.maladies,
                    "medicaments":     alerte.medicaments,
                    "medecin_referent":alerte.medecin_referent,
                    "latitude":        alerte.latitude,
                    "longitude":       alerte.longitude,
                }
                return SOSIAProPendingOut(
                    has_pending    = True,
                    check_id       = check.id,
                    action         = "auto_sos",
                    reminder_count = 2,
                    sent_at        = check.sent_at,
                    sos_data       = sos_data,
                )

            # En attente de réponse (< 60s ou états intermédiaires)
            return SOSIAProPendingOut(
                has_pending    = True,
                check_id       = check.id,
                action         = "waiting",
                reminder_count = check.reminder_count,
                sent_at        = check.sent_at,
            )

    # ─── Cas 2 : est-ce l'heure du prochain check ? ──────────────────
    if cfg.next_check_at:
        next_ts = cfg.next_check_at
        if next_ts.tzinfo is None:
            next_ts = next_ts.replace(tzinfo=timezone.utc)
        if now >= next_ts:
            new_check = SOSIAProCheck(user_id=current_user.id)
            db.add(new_check)
            db.flush()

            cfg.current_check_id = new_check.id
            cfg.last_check_at    = now
            db.commit()
            db.refresh(new_check)

            return SOSIAProPendingOut(
                has_pending    = True,
                check_id       = new_check.id,
                action         = "new_check",
                reminder_count = 0,
                sent_at        = new_check.sent_at,
            )

    return SOSIAProPendingOut(has_pending=False)


@app.post(
    "/client/sos-ia-pro/repondre",
    response_model=SOSIAProRepondreOut,
    tags=["SOS IA Pro"],
)
def repondre_sos_ia_pro(
    data: SOSIAProRepondreIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Enregistrer la réponse de l'utilisateur à une notification SOS IA Pro.
      ok          → prochain check dans interval_minutes
      not_ok_self → prochain check dans max(10, interval/2) minutes
      emergency   → déclenchement immédiat du SOS
    """
    check = db.query(SOSIAProCheck).filter(
        SOSIAProCheck.id      == data.check_id,
        SOSIAProCheck.user_id == current_user.id,
    ).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check SOS IA Pro introuvable.")
    if check.responded_at:
        raise HTTPException(status_code=400, detail="Ce check a déjà été répondu.")

    cfg = _sos_ia_get_or_create_config(current_user.id, db)
    now = datetime.now(timezone.utc)
    check.responded_at  = now
    check.response_type = data.response
    sos_alerte_data     = None

    if data.response == "ok":
        cfg.next_check_at    = now + timedelta(minutes=cfg.interval_minutes)
        cfg.current_check_id = None
        message = f"Parfait ! Prochain check dans {cfg.interval_minutes} min."

    elif data.response == "not_ok_self":
        reduced_min          = max(10, cfg.interval_minutes // 2)
        cfg.next_check_at    = now + timedelta(minutes=reduced_min)
        cfg.current_check_id = None
        message = f"Compris. On re-vérifie dans {reduced_min} min."

    elif data.response == "emergency":
        alerte = _sos_ia_build_alerte(
            current_user, db,
            latitude  = data.latitude,
            longitude = data.longitude,
            note      = (
                "🤖 SOS IA Pro – L'utilisateur a déclenché l'urgence "
                "via la notification de vérification automatique."
            ),
        )
        check.sos_triggered  = True
        check.sos_alerte_id  = alerte.id
        cfg.is_active        = False
        cfg.current_check_id = None
        cfg.next_check_at    = None

        if data.latitude and data.longitude:
            db.add(LocalisationClient(
                user_id   = current_user.id,
                latitude  = data.latitude,
                longitude = data.longitude,
                est_sos   = True,
            ))

        db.commit()
        db.refresh(alerte)

        sos_alerte_data = {
            "id":              alerte.id,
            "nom_complet":     alerte.nom_complet,
            "telephone":       alerte.telephone,
            "groupe_sanguin":  alerte.groupe_sanguin,
            "allergies":       alerte.allergies,
            "maladies":        alerte.maladies,
            "medicaments":     alerte.medicaments,
            "medecin_referent":alerte.medecin_referent,
            "latitude":        alerte.latitude,
            "longitude":       alerte.longitude,
        }
        message = "SOS déclenché. Les secours ont été alertés."
    else:
        raise HTTPException(
            status_code=400,
            detail="Réponse invalide. Valeurs acceptées : ok | not_ok_self | emergency"
        )

    cfg.updated_at = now
    db.commit()

    return SOSIAProRepondreOut(
        success       = True,
        response      = data.response,
        next_check_at = cfg.next_check_at,
        message       = message,
        sos_alerte    = sos_alerte_data,
    )


@app.get(
    "/client/sos-ia-pro/historique",
    tags=["SOS IA Pro"],
)
def historique_sos_ia_pro(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Historique des vérifications SOS IA Pro de l'utilisateur connecté."""
    checks = (
        db.query(SOSIAProCheck)
        .filter(SOSIAProCheck.user_id == current_user.id)
        .order_by(SOSIAProCheck.sent_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":                c.id,
            "sent_at":           c.sent_at.isoformat()      if c.sent_at      else None,
            "responded_at":      c.responded_at.isoformat() if c.responded_at else None,
            "response_type":     c.response_type,
            "reminder_count":    c.reminder_count,
            "contacts_notified": c.contacts_notified,
            "sos_triggered":     c.sos_triggered,
        }
        for c in checks
    ]


@app.get(
    "/admin/sos-ia-pro",
    tags=["Admin – SOS IA Pro"],
)
def admin_liste_sos_ia_pro(
    is_active: Optional[bool] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Liste les clients avec SOS IA Pro actif (admin)."""
    q = db.query(SOSIAProConfig, User).join(User, SOSIAProConfig.user_id == User.id)
    if is_active is not None:
        q = q.filter(SOSIAProConfig.is_active == is_active)
    rows = q.order_by(SOSIAProConfig.updated_at.desc()).all()
    return [
        {
            "user_id":          u.id,
            "nom_complet":      f"{u.prenom} {u.nom}",
            "telephone":        u.telephone,
            "interval_minutes": cfg.interval_minutes,
            "is_active":        cfg.is_active,
            "next_check_at":    cfg.next_check_at.isoformat() if cfg.next_check_at else None,
            "last_check_at":    cfg.last_check_at.isoformat() if cfg.last_check_at else None,
        }
        for cfg, u in rows
    ]


class Ambulance(Base):
    __tablename__ = "ambulances"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    immatriculation = Column(String, nullable=False, unique=True)
    modele          = Column(String, nullable=True)
    annee           = Column(Integer, nullable=True)
    statut          = Column(String, default="disponible")  # disponible | en_mission | maintenance
    garage          = Column(String, nullable=True)
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    adresse_details       = Column(JSON, nullable=True)
    derniere_position_at  = Column(DateTime(timezone=True), nullable=True)

    # Relations
    compte          = relationship("CompteAmbulance", back_populates="ambulance", uselist=False)
    missions        = relationship("MissionAmbulance", back_populates="ambulance")
    inventaire      = relationship("InventaireAmbulance", back_populates="ambulance")


class CompteAmbulance(Base):
    """Compte de connexion propre à chaque ambulance/ambulancier."""
    __tablename__ = "comptes_ambulances"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ambulance_id    = Column(String, ForeignKey("ambulances.id"), nullable=False, unique=True)
    username        = Column(String, nullable=False, unique=True)   # ex: AMB-001
    hashed_password = Column(String, nullable=False)
    ambulancier_nom = Column(String, nullable=True)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ambulance = relationship("Ambulance", back_populates="compte")


class MissionAmbulance(Base):
    __tablename__ = "missions_ambulances"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ambulance_id    = Column(String, ForeignKey("ambulances.id"), nullable=False)
    sos_alerte_id   = Column(String, ForeignKey("sos_alertes.id"), nullable=True)
    destination     = Column(String, nullable=False)
    motif           = Column(String, nullable=True)       # evacuation | transfert | autre
    statut          = Column(String, default="en_cours")  # en_cours | arrive | retour | termine
    lat_depart      = Column(Float, nullable=True)
    lng_depart      = Column(Float, nullable=True)
    lat_destination = Column(Float, nullable=True)
    lng_destination = Column(Float, nullable=True)
    heure_depart    = Column(DateTime, nullable=True)
    heure_arrivee   = Column(DateTime, nullable=True)
    heure_retour    = Column(DateTime, nullable=True)
    distance_km     = Column(Float, nullable=True)
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ambulance  = relationship("Ambulance", back_populates="missions")
    positions  = relationship("PositionAmbulance", back_populates="mission")


class PositionAmbulance(Base):
    """Trace GPS en temps réel pendant une mission."""
    __tablename__ = "positions_ambulances"
    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ambulance_id = Column(String, ForeignKey("ambulances.id"), nullable=False)
    mission_id   = Column(String, ForeignKey("missions_ambulances.id"), nullable=True)
    latitude     = Column(Float, nullable=False)
    longitude    = Column(Float, nullable=False)
    vitesse_kmh  = Column(Float, nullable=True)
    enregistre_a = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    adresse_details = Column(JSON, nullable=True)


    mission = relationship("MissionAmbulance", back_populates="positions")


class InventaireAmbulance(Base):
    __tablename__ = "inventaire_ambulances"
    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ambulance_id = Column(String, ForeignKey("ambulances.id"), nullable=False)
    equipement   = Column(String, nullable=False)   # ex: Défibrillateur, Brancard…
    quantite     = Column(Integer, default=1)
    etat         = Column(String, default="bon")    # bon | a_verifier | hors_service
    derniere_verif = Column(String, nullable=True)  # date YYYY-MM-DD
    notes        = Column(Text, nullable=True)

    ambulance = relationship("Ambulance", back_populates="inventaire")


# ════════════════════════════════════════════════
# SCHÉMAS AMBULANCES
# ════════════════════════════════════════════════

class AmbulanceIn(BaseModel):
    immatriculation: str
    modele:          Optional[str] = None
    annee:           Optional[int] = None
    garage:          Optional[str] = None
    notes:           Optional[str] = None

class AmbulanceOut(AmbulanceIn):
    id:         str
    statut:     str
    created_at: datetime
    class Config: from_attributes = True

class CompteAmbulanceIn(BaseModel):
    username:        str
    password:        str
    ambulancier_nom: Optional[str] = None

class MissionDemarrerIn(BaseModel):
    destination:     str
    motif:           Optional[str] = "evacuation"
    lat_depart:      Optional[float] = None
    lng_depart:      Optional[float] = None
    lat_destination: Optional[float] = None
    lng_destination: Optional[float] = None
    sos_alerte_id:   Optional[str]   = None
    notes:           Optional[str]   = None

class MissionOut(BaseModel):
    id:              str
    ambulance_id:    str
    destination:     str
    motif:           Optional[str]
    statut:          str
    lat_depart:      Optional[float]
    lng_depart:      Optional[float]
    heure_depart:    Optional[datetime]
    heure_arrivee:   Optional[datetime]
    heure_retour:    Optional[datetime]
    distance_km:     Optional[float]
    notes:           Optional[str]
    created_at:      datetime
    class Config: from_attributes = True

class PositionIn(BaseModel):
    latitude:    float
    longitude:   float
    vitesse_kmh: Optional[float] = None
    adresse_details: Optional[dict] = None   

class InventaireIn(BaseModel):
    equipement:      str
    quantite:        Optional[int] = 1
    etat:            Optional[str] = "bon"
    derniere_verif:  Optional[str] = None
    notes:           Optional[str] = None

class InventaireOut(InventaireIn):
    id:          str
    ambulance_id: str
    class Config: from_attributes = True


# ════════════════════════════════════════════════
# AUTH AMBULANCE — LOGIN DÉDIÉ
# ════════════════════════════════════════════════

class AmbulanceLoginOut(BaseModel):
    access_token:    str
    token_type:      str = "bearer"
    ambulance_id:    str
    immatriculation: str
    ambulancier_nom: Optional[str]

@app.post("/ambulance/login", response_model=AmbulanceLoginOut, tags=["Ambulances"])
def ambulance_login(
    form: OAuth2PasswordRequestForm = Depends(),
    db:   Session = Depends(get_db)
):
    """Connexion depuis le dashboard ambulance (username = AMB-XXX)."""
    compte = db.query(CompteAmbulance).filter(
        CompteAmbulance.username == form.username
    ).first()
    if not compte or not verify_password(form.password, compte.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not compte.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    token = create_access_token(
        {"sub": compte.id, "type": "ambulance"},
        timedelta(hours=12)
    )
    return AmbulanceLoginOut(
        access_token=token,
        ambulance_id=compte.ambulance_id,
        immatriculation=compte.ambulance.immatriculation,
        ambulancier_nom=compte.ambulancier_nom,
    )


def get_current_ambulance(
    token: str = Depends(oauth2_scheme),
    db:    Session = Depends(get_db)
) -> CompteAmbulance:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "ambulance":
            raise HTTPException(status_code=403, detail="Token non ambulance")
        compte_id = payload.get("sub")
        compte = db.query(CompteAmbulance).filter(
            CompteAmbulance.id == compte_id
        ).first()
        if not compte:
            raise HTTPException(status_code=401, detail="Compte introuvable")
        return compte
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")


# ════════════════════════════════════════════════
# CRUD AMBULANCES (admin)
# ════════════════════════════════════════════════

@app.post("/admin/ambulances", response_model=AmbulanceOut, status_code=201, tags=["Ambulances"])
def creer_ambulance(
    data:  AmbulanceIn,
    admin: User    = Depends(get_admin_user),
    db:    Session = Depends(get_db)
):
    amb = Ambulance(**data.model_dump())
    db.add(amb)
    db.commit()
    db.refresh(amb)
    return amb

@app.get("/admin/ambulances", response_model=List[AmbulanceOut], tags=["Ambulances"])
def lister_ambulances(
    admin: User    = Depends(get_admin_user),
    db:    Session = Depends(get_db)
):
    return db.query(Ambulance).order_by(Ambulance.created_at.desc()).all()

@app.patch("/admin/ambulances/{amb_id}", response_model=AmbulanceOut, tags=["Ambulances"])
def modifier_ambulance(
    amb_id: str,
    data:   AmbulanceIn,
    admin:  User    = Depends(get_admin_user),
    db:     Session = Depends(get_db)
):
    amb = db.query(Ambulance).filter(Ambulance.id == amb_id).first()
    if not amb:
        raise HTTPException(status_code=404, detail="Ambulance introuvable")
    for f, v in data.model_dump(exclude_none=True).items():
        setattr(amb, f, v)
    db.commit(); db.refresh(amb)
    return amb

@app.delete("/admin/ambulances/{amb_id}", status_code=204, tags=["Ambulances"])
def supprimer_ambulance(
    amb_id: str,
    admin:  User    = Depends(get_admin_user),
    db:     Session = Depends(get_db)
):
    amb = db.query(Ambulance).filter(Ambulance.id == amb_id).first()
    if not amb:
        raise HTTPException(status_code=404, detail="Ambulance introuvable")
    db.delete(amb); db.commit()


# ─── Créer le compte de connexion d'une ambulance ───────────

@app.post("/admin/ambulances/{amb_id}/compte", tags=["Ambulances"])
def creer_compte_ambulance(
    amb_id: str,
    data:   CompteAmbulanceIn,
    admin:  User    = Depends(get_admin_user),
    db:     Session = Depends(get_db)
):
    if db.query(CompteAmbulance).filter(CompteAmbulance.ambulance_id == amb_id).first():
        raise HTTPException(status_code=400, detail="Ce compte existe déjà")
    compte = CompteAmbulance(
        ambulance_id    = amb_id,
        username        = data.username,
        hashed_password = hash_password(data.password),
        ambulancier_nom = data.ambulancier_nom,
    )
    db.add(compte); db.commit(); db.refresh(compte)
    return {"message": "Compte créé", "username": data.username}


# ════════════════════════════════════════════════
# MISSIONS — depuis le dashboard ambulance
# ════════════════════════════════════════════════

@app.post("/ambulance/missions/demarrer", response_model=MissionOut, status_code=201, tags=["Ambulances"])
def demarrer_mission(
    data:   MissionDemarrerIn,
    compte: CompteAmbulance = Depends(get_current_ambulance),
    db:     Session         = Depends(get_db)
):
    """L'ambulancier appuie sur DÉMARRER → mission créée, ambulance en_mission."""
    mission = MissionAmbulance(
        ambulance_id    = compte.ambulance_id,
        destination     = data.destination,
        motif           = data.motif,
        statut          = "en_cours",
        lat_depart      = data.lat_depart,
        lng_depart      = data.lng_depart,
        lat_destination = data.lat_destination,
        lng_destination = data.lng_destination,
        sos_alerte_id   = data.sos_alerte_id,
        heure_depart    = datetime.now(timezone.utc),
        notes           = data.notes,
    )
    db.add(mission)
    # Mettre à jour le statut de l'ambulance
    db.query(Ambulance).filter(
        Ambulance.id == compte.ambulance_id
    ).update({"statut": "en_mission"})
    db.commit(); db.refresh(mission)
    return mission


@app.patch("/ambulance/missions/{mission_id}/arrive", response_model=MissionOut, tags=["Ambulances"])
def ambulance_arrivee_destination(
    mission_id: str,
    lat:        Optional[float] = None,
    lng:        Optional[float] = None,
    compte:     CompteAmbulance = Depends(get_current_ambulance),
    db:         Session         = Depends(get_db)
):
    """L'ambulancier appuie sur ARRIVÉ → heure d'arrivée enregistrée."""
    mission = db.query(MissionAmbulance).filter(
        MissionAmbulance.id          == mission_id,
        MissionAmbulance.ambulance_id == compte.ambulance_id,
    ).first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    mission.statut        = "arrive"
    mission.heure_arrivee = datetime.now(timezone.utc)
    if lat: mission.lat_destination = lat
    if lng: mission.lng_destination = lng
    db.commit(); db.refresh(mission)
    return mission


@app.patch("/ambulance/missions/{mission_id}/retour", response_model=MissionOut, tags=["Ambulances"])
def ambulance_retour_garage(
    mission_id: str,
    distance_km: Optional[float] = None,
    compte:     CompteAmbulance  = Depends(get_current_ambulance),
    db:         Session          = Depends(get_db)
):
    """L'ambulancier appuie sur RETOUR AU GARAGE → mission terminée."""
    mission = db.query(MissionAmbulance).filter(
        MissionAmbulance.id          == mission_id,
        MissionAmbulance.ambulance_id == compte.ambulance_id,
    ).first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    mission.statut      = "termine"
    mission.heure_retour = datetime.now(timezone.utc)
    if distance_km: mission.distance_km = distance_km
    # Remettre l'ambulance disponible
    db.query(Ambulance).filter(
        Ambulance.id == compte.ambulance_id
    ).update({"statut": "disponible"})
    db.commit(); db.refresh(mission)
    return mission




@app.post("/ambulance/position", tags=["Ambulances"])
def enregistrer_position(
    data: PositionIn,
    ambulance: CompteAmbulance = Depends(get_current_ambulance),
    db: Session = Depends(get_db)
):
    pos = PositionAmbulance(
        ambulance_id=ambulance.ambulance_id,
        latitude=data.latitude,
        longitude=data.longitude,
        adresse_details=data.adresse_details   # ← AJOUTER
    )
    db.add(pos)
    # Mettre aussi à jour la dernière position connue sur l'ambulance
    amb = db.query(Ambulance).filter(Ambulance.id == ambulance.ambulance_id).first()
    if amb:
        amb.latitude        = data.latitude
        amb.longitude       = data.longitude
        amb.adresse_details = data.adresse_details  # ← si ce champ existe sur Ambulance
        amb.derniere_position_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.get("/ambulance/missions/en_cours", response_model=Optional[MissionOut], tags=["Ambulances"])
def mission_en_cours(
    compte: CompteAmbulance = Depends(get_current_ambulance),
    db:     Session         = Depends(get_db)
):
    """Récupère la mission active de l'ambulancier connecté."""
    return db.query(MissionAmbulance).filter(
        MissionAmbulance.ambulance_id == compte.ambulance_id,
        MissionAmbulance.statut.in_(["en_cours", "arrive"])
    ).order_by(MissionAmbulance.created_at.desc()).first()


@app.get("/ambulance/missions/historique", response_model=List[MissionOut], tags=["Ambulances"])
def historique_missions_ambulance(
    limit:  int             = 50,
    compte: CompteAmbulance = Depends(get_current_ambulance),
    db:     Session         = Depends(get_db)
):
    return db.query(MissionAmbulance).filter(
        MissionAmbulance.ambulance_id == compte.ambulance_id
    ).order_by(MissionAmbulance.created_at.desc()).limit(limit).all()


# ════════════════════════════════════════════════
# INVENTAIRE (ambulancier + admin)
# ════════════════════════════════════════════════

@app.get("/ambulance/inventaire", response_model=List[InventaireOut], tags=["Ambulances"])
def get_inventaire(
    compte: CompteAmbulance = Depends(get_current_ambulance),
    db:     Session         = Depends(get_db)
):
    return db.query(InventaireAmbulance).filter(
        InventaireAmbulance.ambulance_id == compte.ambulance_id
    ).all()

@app.post("/ambulance/inventaire", response_model=InventaireOut, status_code=201, tags=["Ambulances"])
def ajouter_equipement(
    data:   InventaireIn,
    compte: CompteAmbulance = Depends(get_current_ambulance),
    db:     Session         = Depends(get_db)
):
    item = InventaireAmbulance(ambulance_id=compte.ambulance_id, **data.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return item

@app.patch("/ambulance/inventaire/{item_id}", response_model=InventaireOut, tags=["Ambulances"])
def modifier_equipement(
    item_id: str,
    data:    InventaireIn,
    compte:  CompteAmbulance = Depends(get_current_ambulance),
    db:      Session         = Depends(get_db)
):
    item = db.query(InventaireAmbulance).filter(
        InventaireAmbulance.id          == item_id,
        InventaireAmbulance.ambulance_id == compte.ambulance_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Équipement introuvable")
    for f, v in data.model_dump(exclude_none=True).items():
        setattr(item, f, v)
    db.commit(); db.refresh(item)
    return item


# ════════════════════════════════════════════════
# ROUTES ADMIN — VISION GLOBALE
# ════════════════════════════════════════════════

@app.get("/admin/ambulances/{amb_id}/missions", response_model=List[MissionOut], tags=["Ambulances"])
def admin_missions_ambulance(
    amb_id: str,
    admin:  User    = Depends(get_admin_user),
    db:     Session = Depends(get_db)
):
    return db.query(MissionAmbulance).filter(
        MissionAmbulance.ambulance_id == amb_id
    ).order_by(MissionAmbulance.created_at.desc()).all()

@app.get("/admin/ambulances/{amb_id}/positions", tags=["Ambulances"])
def admin_positions_ambulance(
    amb_id:     str,
    mission_id: Optional[str] = None,
    admin:      User          = Depends(get_admin_user),
    db:         Session       = Depends(get_db)
):
    q = db.query(PositionAmbulance).filter(PositionAmbulance.ambulance_id == amb_id)
    if mission_id:
        q = q.filter(PositionAmbulance.mission_id == mission_id)
    return q.order_by(PositionAmbulance.enregistre_a.desc()).limit(500).all()

@app.get("/admin/ambulances/{amb_id}/inventaire", response_model=List[InventaireOut], tags=["Ambulances"])
def admin_inventaire_ambulance(
    amb_id: str,
    admin:  User    = Depends(get_admin_user),
    db:     Session = Depends(get_db)
):
    return db.query(InventaireAmbulance).filter(
        InventaireAmbulance.ambulance_id == amb_id
    ).all()

@app.get("/admin/missions/actives", tags=["Ambulances"])
def admin_toutes_missions_actives(
    admin: User    = Depends(get_admin_user),
    db:    Session = Depends(get_db)
):
    """Carte temps réel : toutes les ambulances en mission."""
    missions = db.query(MissionAmbulance, Ambulance).join(
        Ambulance, MissionAmbulance.ambulance_id == Ambulance.id
    ).filter(
        MissionAmbulance.statut.in_(["en_cours", "arrive"])
    ).all()
    return [
        {
            "mission_id":    m.id,
            "ambulance_id":  a.id,
            "immatriculation": a.immatriculation,
            "destination":   m.destination,
            "statut":        m.statut,
            "heure_depart":  m.heure_depart.isoformat() if m.heure_depart else None,
            "lat_depart":    m.lat_depart,
            "lng_depart":    m.lng_depart,
        }
        for m, a in missions
    ]

@app.get("/admin/ambulances/stats", tags=["Ambulances"])
def stats_ambulances(
    admin: User    = Depends(get_admin_user),
    db:    Session = Depends(get_db)
):
    total        = db.query(Ambulance).count()
    disponibles  = db.query(Ambulance).filter(Ambulance.statut=="disponible").count()
    en_mission   = db.query(Ambulance).filter(Ambulance.statut=="en_mission").count()
    maintenance  = db.query(Ambulance).filter(Ambulance.statut=="maintenance").count()
    total_missions = db.query(MissionAmbulance).count()
    mois = datetime.now().strftime("%Y-%m")
    missions_mois  = db.query(MissionAmbulance).filter(
        MissionAmbulance.created_at >= datetime.now().replace(day=1)
    ).count()
    return {
        "total":           total,
        "disponibles":     disponibles,
        "en_mission":      en_mission,
        "maintenance":     maintenance,
        "total_missions":  total_missions,
        "missions_ce_mois": missions_mois,
    }






class Clinique(Base):
    __tablename__ = "cliniques"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom             = Column(String, nullable=False)
    type            = Column(String, default="clinique")  # clinique | hôpital | centre
    adresse         = Column(String)
    telephone       = Column(String)
    email           = Column(String)
    statut          = Column(String, default="active")  # active | inactive
    created_at      = Column(DateTime, default=datetime.utcnow)

class CompteCliique(Base):
    __tablename__ = "comptes_clinique"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    clinique_id     = Column(String, ForeignKey("cliniques.id"))
    username        = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

class SOSTransfert(Base):
    __tablename__ = "sos_transferts"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sos_id          = Column(String, ForeignKey("sos_alertes.id"))
    clinique_id     = Column(String, ForeignKey("cliniques.id"))
    statut          = Column(String, default="envoyé")
    # envoyé | pris_en_charge | en_traitement | terminé
    note_admin      = Column(String)
    created_at      = Column(DateTime, default=datetime.utcnow)
    prise_en_charge_at = Column(DateTime)
    fin_at          = Column(DateTime)

class EtapeTraitement(Base):
    __tablename__ = "etapes_traitement"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    transfert_id    = Column(String, ForeignKey("sos_transferts.id"))
    description     = Column(String, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)


from fastapi import Body

class CliniqueIn(BaseModel):
    nom:       str
    type:      Optional[str] = "clinique"
    telephone: Optional[str] = None
    email:     Optional[str] = None
    adresse:   Optional[str] = None

class CompteCliniqueIn(BaseModel):
    username: str
    password: str

class TransfertNoteIn(BaseModel):
    note: Optional[str] = None

class EtapeIn(BaseModel):
    description: str




@app.post("/admin/cliniques", tags=["Cliniques"])
def creer_clinique(
    data: CliniqueIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    c = Clinique(
        nom=data.nom, type=data.type, telephone=data.telephone,
        email=data.email, adresse=data.adresse
    )
    db.add(c); db.commit(); db.refresh(c)
    return c

@app.get("/admin/cliniques", tags=["Cliniques"])
def lister_cliniques(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    return db.query(Clinique).all()

@app.patch("/admin/cliniques/{clin_id}", tags=["Cliniques"])
def modifier_clinique(
    clin_id: str,
    data: CliniqueIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    c = db.query(Clinique).filter(Clinique.id == clin_id).first()
    if not c: raise HTTPException(404, "Clinique introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    db.commit(); db.refresh(c)
    return c

@app.delete("/admin/cliniques/{clin_id}", status_code=204, tags=["Cliniques"])
def supprimer_clinique(
    clin_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    c = db.query(Clinique).filter(Clinique.id == clin_id).first()
    if not c: raise HTTPException(404, "Clinique introuvable")
    db.delete(c); db.commit()

@app.post("/admin/cliniques/{clin_id}/compte", tags=["Cliniques"])
def creer_compte_clinique(
    clin_id: str,
    data: CompteCliniqueIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    if db.query(CompteCliique).filter(CompteCliique.username == data.username).first():
        raise HTTPException(400, "Username déjà utilisé")
    compte = CompteCliique(
        clinique_id=clin_id,
        username=data.username,
        hashed_password=hash_password(data.password)
    )
    db.add(compte); db.commit(); db.refresh(compte)
    return {"ok": True, "username": data.username}

@app.post("/admin/sos/{sos_id}/transferer/{clinique_id}", tags=["Cliniques"])
def transferer_sos(
    sos_id: str,
    clinique_id: str,
    data: TransfertNoteIn = Body(default=TransfertNoteIn()),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    t = SOSTransfert(sos_id=sos_id, clinique_id=clinique_id, note_admin=data.note)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "statut": t.statut, "created_at": str(t.created_at)}

@app.get("/admin/sos/{sos_id}/transferts", tags=["Cliniques"])
def transferts_du_sos(
    sos_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    transferts = db.query(SOSTransfert).filter(SOSTransfert.sos_id == sos_id).all()
    result = []
    for t in transferts:
        c = db.query(Clinique).filter(Clinique.id == t.clinique_id).first()
        etapes = db.query(EtapeTraitement).filter(
            EtapeTraitement.transfert_id == t.id
        ).order_by(EtapeTraitement.created_at).all()
        result.append({
            "id": t.id, "statut": t.statut,
            "clinique_nom": c.nom if c else "—",
            "note_admin": t.note_admin,
            "created_at": str(t.created_at),
            "etapes": [{"description": e.description,
                        "created_at": str(e.created_at)} for e in etapes]
        })
    return result

@app.get("/admin/cliniques/stats", tags=["Cliniques"])
def stats_cliniques(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    return {
        "total":              db.query(Clinique).count(),
        "actives":            db.query(Clinique).filter(Clinique.statut=="active").count(),
        "transferts_actifs":  db.query(SOSTransfert).filter(
            SOSTransfert.statut.in_(["envoyé","pris_en_charge","en_traitement"])).count(),
        "transferts_termines": db.query(SOSTransfert).filter(
            SOSTransfert.statut=="terminé").count(),
    }

# ══ ROUTES CLINIQUE ══
@app.post("/clinique/login", tags=["Cliniques"])
def login_clinique(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    compte = db.query(CompteCliique).filter(
        CompteCliique.username == form.username
    ).first()
    if not compte or not verify_password(form.password, compte.hashed_password):
        raise HTTPException(401, "Identifiants incorrects")
    token = create_access_token(
        {"sub": compte.clinique_id, "type": "clinique"},
        timedelta(hours=12)
    )
    clinique = db.query(Clinique).filter(Clinique.id == compte.clinique_id).first()
    return {
        "access_token": token, "token_type": "bearer",
        "clinique_id":  compte.clinique_id,
        "clinique_nom": clinique.nom if clinique else "—",
        "is_clinique":  True
    }

def get_current_clinique(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Clinique:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "clinique":
            raise HTTPException(403, "Token non clinique")
        clinique_id = payload.get("sub")
    except JWTError:
        raise HTTPException(401, "Token invalide")
    c = db.query(Clinique).filter(Clinique.id == clinique_id).first()
    if not c: raise HTTPException(401, "Clinique introuvable")
    return c

@app.get("/clinique/sos-entrants", tags=["Cliniques"])
def sos_entrants_clinique(
    clinique: Clinique = Depends(get_current_clinique),
    db: Session = Depends(get_db)
):
    transferts = db.query(SOSTransfert).filter(
        SOSTransfert.clinique_id == clinique.id,
        SOSTransfert.statut != "terminé"
    ).order_by(SOSTransfert.created_at.desc()).all()
    result = []
    for t in transferts:
        sos = db.query(SOSAlerte).filter(SOSAlerte.id == t.sos_id).first()
        etapes = db.query(EtapeTraitement).filter(
            EtapeTraitement.transfert_id == t.id
        ).order_by(EtapeTraitement.created_at).all()
        row = {
            "transfert_id": t.id,
            "statut":       t.statut,
            "note_admin":   t.note_admin,
            "created_at":   str(t.created_at),
            "prise_en_charge_at": str(t.prise_en_charge_at) if t.prise_en_charge_at else None,
            "etapes": [{"id": e.id, "description": e.description,
                        "created_at": str(e.created_at)} for e in etapes],
        }
        if sos:
            row.update({
                "nom_complet":     sos.nom_complet,
                "telephone":       sos.telephone,
                "groupe_sanguin":  sos.groupe_sanguin,
                "allergies":       sos.allergies,
                "maladies":        sos.maladies,
                "medicaments":     sos.medicaments,
                "medecin_referent":sos.medecin_referent,
                "latitude":        sos.latitude,
                "longitude":       sos.longitude,
            })
        result.append(row)
    return result

@app.patch("/clinique/transferts/{transfert_id}/prise-en-charge", tags=["Cliniques"])
def prise_en_charge(
    transfert_id: str,
    clinique: Clinique = Depends(get_current_clinique),
    db: Session = Depends(get_db)
):
    t = db.query(SOSTransfert).filter(
        SOSTransfert.id == transfert_id,
        SOSTransfert.clinique_id == clinique.id
    ).first()
    if not t: raise HTTPException(404, "Transfert introuvable")
    t.statut = "pris_en_charge"
    t.prise_en_charge_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(t)
    return {"id": t.id, "statut": t.statut}

@app.post("/clinique/transferts/{transfert_id}/etapes", tags=["Cliniques"])
def ajouter_etape(
    transfert_id: str,
    data: EtapeIn,
    clinique: Clinique = Depends(get_current_clinique),
    db: Session = Depends(get_db)
):
    t = db.query(SOSTransfert).filter(
        SOSTransfert.id == transfert_id,
        SOSTransfert.clinique_id == clinique.id
    ).first()
    if not t: raise HTTPException(404, "Transfert introuvable")
    if t.statut == "pris_en_charge":
        t.statut = "en_traitement"
    etape = EtapeTraitement(transfert_id=transfert_id, description=data.description)
    db.add(etape); db.commit(); db.refresh(etape)
    return {"id": etape.id, "description": etape.description,
            "created_at": str(etape.created_at)}

@app.patch("/clinique/transferts/{transfert_id}/fin", tags=["Cliniques"])
def fin_traitement(
    transfert_id: str,
    clinique: Clinique = Depends(get_current_clinique),
    db: Session = Depends(get_db)
):
    t = db.query(SOSTransfert).filter(
        SOSTransfert.id == transfert_id,
        SOSTransfert.clinique_id == clinique.id
    ).first()
    if not t: raise HTTPException(404, "Transfert introuvable")
    t.statut = "terminé"
    t.fin_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(t)
    return {"id": t.id, "statut": t.statut}

@app.get("/clinique/historique", tags=["Cliniques"])
def historique_clinique(
    clinique: Clinique = Depends(get_current_clinique),
    db: Session = Depends(get_db)
):
    transferts = db.query(SOSTransfert).filter(
        SOSTransfert.clinique_id == clinique.id,
        SOSTransfert.statut == "terminé"
    ).order_by(SOSTransfert.fin_at.desc()).all()
    result = []
    for t in transferts:
        sos = db.query(SOSAlerte).filter(SOSAlerte.id == t.sos_id).first()
        etapes = db.query(EtapeTraitement).filter(
            EtapeTraitement.transfert_id == t.id
        ).order_by(EtapeTraitement.created_at).all()
        row = {
            "transfert_id": t.id,
            "statut":       t.statut,
            "created_at":   str(t.created_at),
            "fin_at":       str(t.fin_at) if t.fin_at else None,
            "etapes": [{"description": e.description,
                        "created_at": str(e.created_at)} for e in etapes],
        }
        if sos:
            row.update({
                "nom_complet":    sos.nom_complet,
                "groupe_sanguin": sos.groupe_sanguin,
                "telephone":      sos.telephone,
            })
        result.append(row)
    return result





# ══ MODÈLE AVIS ══
class Avis(Base):
    __tablename__ = "avis"
    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    note        = Column(Integer, nullable=False)  
    message     = Column(Text, nullable=False)
    approuve    = Column(Boolean, default=True)    
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    user        = relationship("User", backref="avis")

class AvisIn(BaseModel):
    note:    int       # 1–5
    message: str

@app.post("/avis", status_code=201, tags=["Avis"])
def soumettre_avis(
    data: AvisIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not (1 <= data.note <= 5):
        raise HTTPException(400, "Note entre 1 et 5")
    a = Avis(user_id=current_user.id, note=data.note, message=data.message)
    db.add(a); db.commit(); db.refresh(a)
    return {"id": a.id, "note": a.note, "message": a.message}

@app.get("/avis", tags=["Avis"])
def lister_avis(limit: int = 20, db: Session = Depends(get_db)):
    """Avis approuvés — public."""
    rows = (
        db.query(Avis, User)
        .join(User, Avis.user_id == User.id)
        .filter(Avis.approuve == True)
        .order_by(Avis.created_at.desc())
        .limit(limit).all()
    )
    return [{
        "id":         a.id,
        "note":       a.note,
        "message":    a.message,
        "nom":        f"{u.prenom} {u.nom}",
        "quartier":   u.quartier or "",
        "created_at": a.created_at.isoformat(),
    } for a, u in rows]

# ══ ROUTE PUBLIQUE CLINIQUES ══
@app.get("/cliniques-partenaires", tags=["Public"])
def cliniques_publiques(db: Session = Depends(get_db)):
    """Liste des cliniques partenaires actives — public."""
    clins = db.query(Clinique).filter(Clinique.statut == "active").all()
    return [{"id": c.id, "nom": c.nom, "type": c.type,
             "telephone": c.telephone, "adresse": c.adresse} for c in clins]




def migrate_colonnes_manquantes():
    with engine.connect() as conn:
        migrations = [
            "ALTER TABLE ambulances ADD COLUMN IF NOT EXISTS latitude FLOAT",
            "ALTER TABLE ambulances ADD COLUMN IF NOT EXISTS longitude FLOAT",
            "ALTER TABLE ambulances ADD COLUMN IF NOT EXISTS adresse_details JSON",
            "ALTER TABLE ambulances ADD COLUMN IF NOT EXISTS derniere_position_at TIMESTAMPTZ",
            "ALTER TABLE positions_ambulances ADD COLUMN IF NOT EXISTS adresse_details JSON",
            "ALTER TABLE positions_ambulances ADD COLUMN IF NOT EXISTS mission_id VARCHAR",
        ]
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                print(f"Migration ignorée : {e}")

migrate_colonnes_manquantes()

# Création de toutes les tables
Base.metadata.create_all(bind=engine)



# ─────────────────────────────────────────────
# LANCEMENT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)