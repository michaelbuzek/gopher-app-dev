# models.py - Gopher Minigolf SQLAlchemy Models (Production Ready)

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from sqlalchemy import func, text, Index
from typing import Dict, List, Optional, Tuple
import os

db = SQLAlchemy()

# ==========================================
# 📍 PLACES TABLE (Minigolf-Plätze)
# ==========================================

class Place(db.Model):
    __tablename__ = 'places'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    track_count = db.Column(db.Integer, nullable=False, default=18)
    is_default = db.Column(db.Boolean, default=False, index=True)
    has_custom_config = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    games = db.relationship('Game', backref='place_obj', lazy='dynamic', foreign_keys='Game.place_id')
    track_configs = db.relationship('TrackConfiguration', backref='place', lazy='dynamic', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        db.CheckConstraint('track_count >= 1 AND track_count <= 50', name='valid_track_count'),
        Index('idx_places_default', 'is_default'),
    )
    
    def __repr__(self):
        return f'<Place {self.name} ({self.track_count} tracks)>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'track_count': self.track_count,
            'is_default': self.is_default,
            'has_custom_config': self.has_custom_config
        }
    
    def get_track_icons(self) -> Dict[int, str]:
        """Returns track icons for all tracks at this place"""
        track_icons = {}
        configs = {tc.track_number: tc for tc in self.track_configs}
        
        for track_num in range(1, self.track_count + 1):
            if track_num in configs and configs[track_num].track_type:
                track_icons[track_num] = configs[track_num].track_type.icon_url
            else:
                track_icons[track_num] = '/static/track-icons/bahn_placeholder.png'
        
        return track_icons
    
    @classmethod
    def get_or_create(cls, name: str, track_count: int = 18) -> 'Place':
        """Get existing place or create new one"""
        place = cls.query.filter_by(name=name).first()
        if not place:
            place = cls(name=name, track_count=track_count)
            db.session.add(place)
            db.session.flush()  # Get ID without committing
        return place

# ==========================================
# 🎯 TRACK TYPES TABLE (Bahn-Typen)
# ==========================================

class TrackType(db.Model):
    __tablename__ = 'track_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.Text)
    icon_url = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    track_configs = db.relationship('TrackConfiguration', backref='track_type', lazy='dynamic')
    
    def __repr__(self):
        return f'<TrackType {self.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon_url': self.icon_url
        }

# ==========================================
# 🔗 TRACK CONFIGURATIONS TABLE (Platz-spezifische Bahn-Konfiguration)
# ==========================================

class TrackConfiguration(db.Model):
    __tablename__ = 'track_configurations'
    
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('places.id', ondelete='CASCADE'), nullable=False)
    track_number = db.Column(db.Integer, nullable=False)
    track_type_id = db.Column(db.Integer, db.ForeignKey('track_types.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('place_id', 'track_number', name='unique_place_track'),
        db.CheckConstraint('track_number >= 1 AND track_number <= 50', name='valid_track_number'),
        Index('idx_track_config_place', 'place_id'),
        Index('idx_track_config_number', 'track_number'),
    )
    
    def __repr__(self):
        return f'<TrackConfig Place:{self.place_id} Track:{self.track_number}>'

# ==========================================
# 🎮 GAMES TABLE (Haupt-Spiele)
# ==========================================

class Game(db.Model):
    __tablename__ = 'games'
    
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=True, index=True)
    place = db.Column(db.String(255), nullable=False, index=True)  # Fallback für neue Plätze
    date = db.Column(db.Date, nullable=False, index=True)
    track_count = db.Column(db.Integer, nullable=False, default=18)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    players = db.relationship('Player', backref='game', lazy='dynamic', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        db.CheckConstraint('track_count >= 1 AND track_count <= 50', name='valid_game_track_count'),
        Index('idx_games_date_desc', 'date', postgresql_using='btree', postgresql_ops={'date': 'DESC'}),
        Index('idx_games_place_date', 'place', 'date'),
    )
    
    def __repr__(self):
        return f'<Game #{self.id}: {self.place} ({self.date})>'
    
    def to_dict(self, include_players=False):
        data = {
            'id': self.id,
            'place_id': self.place_id,
            'place': self.place,
            'date': self.date.strftime('%d.%m.%Y') if isinstance(self.date, date) else str(self.date),
            'track_count': self.track_count,
            'player_count': self.players.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        if include_players:
            data['players'] = [player.to_dict() for player in self.players]
            
        return data
    
    def get_results(self) -> List[Dict]:
        """Get sorted game results with winner information"""
        results = []
        
        for player in self.players:
            total_score = player.get_total_score()
            results.append({
                'player_id': player.id,
                'name': player.name,
                'total': total_score,
                'scores': player.get_scores_dict(),
                'completed_tracks': player.scores.count(),
                'is_winner': False,
                'is_tie': False
            })
        
        # Sort and determine winners (only players with scores > 0)
        valid_results = [r for r in results if r['total'] > 0]
        incomplete_results = [r for r in results if r['total'] == 0]
        
        if valid_results:
            valid_results.sort(key=lambda x: x['total'])
            min_score = valid_results[0]['total']
            winners = [r for r in valid_results if r['total'] == min_score]
            is_tie = len(winners) > 1
            
            for result in valid_results:
                if result['total'] == min_score:
                    result['is_winner'] = True
                    result['is_tie'] = is_tie
        
        return valid_results + incomplete_results
    
    def get_track_icons(self) -> Dict[int, str]:
        """Get track icons for this game"""
        if self.place_obj and self.place_obj.has_custom_config:
            return self.place_obj.get_track_icons()
        
        # Default placeholder for all tracks
        return {
            track_num: '/static/track-icons/bahn_placeholder.png' 
            for track_num in range(1, self.track_count + 1)
        }
    
    @property
    def has_track_config(self) -> bool:
        """Check if this game has custom track configuration"""
        return self.place_obj and self.place_obj.has_custom_config

# ==========================================
# 👥 PLAYERS TABLE (Spieler pro Spiel)
# ==========================================

class Player(db.Model):
    __tablename__ = 'players'
    
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    scores = db.relationship('Score', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        Index('idx_players_game_name', 'game_id', 'name'),
    )
    
    def __repr__(self):
        return f'<Player {self.name} (Game #{self.game_id})>'
    
    def to_dict(self, include_scores=False):
        data = {
            'id': self.id,
            'game_id': self.game_id,
            'name': self.name,
            'total_score': self.get_total_score(),
            'completed_tracks': self.scores.count()
        }
        
        if include_scores:
            data['scores'] = self.get_scores_dict()
            
        return data
    
    def get_total_score(self) -> int:
        """Calculate total score for this player"""
        return sum(score.score_value for score in self.scores)
    
    def get_scores_dict(self) -> Dict[int, int]:
        """Get scores as {track_number: score_value} dict"""
        return {score.track_number: score.score_value for score in self.scores}
    
    def get_score_for_track(self, track_number: int) -> Optional[int]:
        """Get score for specific track"""
        score = self.scores.filter_by(track_number=track_number).first()
        return score.score_value if score else None
    
    def set_score_for_track(self, track_number: int, score_value: int) -> bool:
        """Set score for specific track"""
        try:
            score = self.scores.filter_by(track_number=track_number).first()
            
            if score_value <= 0:
                # Delete score if value is 0 or negative
                if score:
                    db.session.delete(score)
            else:
                # Update or create score
                if score:
                    score.score_value = score_value
                    score.updated_at = datetime.utcnow()
                else:
                    score = Score(
                        player_id=self.id,
                        track_number=track_number,
                        score_value=score_value
                    )
                    db.session.add(score)
            
            return True
        except Exception as e:
            print(f"Error setting score: {e}")
            return False

# ==========================================
# 🏌️ SCORES TABLE (Individual Schläge)
# ==========================================

class Score(db.Model):
    __tablename__ = 'scores'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id', ondelete='CASCADE'), nullable=False, index=True)
    track_number = db.Column(db.Integer, nullable=False, index=True)
    score_value = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('player_id', 'track_number', name='unique_player_track_score'),
        db.CheckConstraint('score_value > 0 AND score_value <= 20', name='valid_score_value'),
        db.CheckConstraint('track_number >= 1 AND track_number <= 50', name='valid_score_track'),
        Index('idx_scores_player_track', 'player_id', 'track_number'),
    )
    
    def __repr__(self):
        return f'<Score Player:{self.player_id} Track:{self.track_number} Value:{self.score_value}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'track_number': self.track_number,
            'score_value': self.score_value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

# ==========================================
# 🚀 DATABASE UTILITIES
# ==========================================

def init_database():
    """Initialize database with tables and default data"""
    try:
        # Create all tables
        db.create_all()
        print("✅ Tables created successfully!")
        
        # Add default data
        seed_default_data()
        
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def seed_default_data():
    """Seed database with default track types and places"""
    try:
        # Check if data already exists
        if TrackType.query.first() or Place.query.first():
            print("⚠️ Default data already exists, skipping...")
            return
        
        # Create default track types
        track_types = [
            TrackType(name='Standard', icon_url='/static/track-icons/bahn_placeholder.png', description='Standard Minigolf Bahn'),
            TrackType(name='Windmühle', icon_url='/static/track-icons/windmill.png', description='Bahn mit Windmühle'),
            TrackType(name='Rampe', icon_url='/static/track-icons/ramp.png', description='Rampen-Bahn'),
            TrackType(name='Schleife', icon_url='/static/track-icons/loop.png', description='Schleifen-Bahn'),
            TrackType(name='Tunnel', icon_url='/static/track-icons/tunnel.png', description='Tunnel-Bahn'),
            TrackType(name='Brücke', icon_url='/static/track-icons/bridge.png', description='Brücken-Bahn'),
            TrackType(name='Kurve', icon_url='/static/track-icons/curve.png', description='Kurven-Bahn'),
            TrackType(name='Hindernis', icon_url='/static/track-icons/obstacle.png', description='Hindernis-Bahn'),
        ]
        
        for track_type in track_types:
            db.session.add(track_type)
        
        # Create default places
        places = [
            Place(name='Bülach', track_count=18, is_default=True),
            Place(name='Zürich Minigolf', track_count=18, is_default=True),
            Place(name='Winterthur Adventure Golf', track_count=14, is_default=False),
            Place(name='Rapperswil Minigolf', track_count=18, is_default=False),
        ]
        
        for place in places:
            db.session.add(place)
        
        db.session.commit()
        print("✅ Default data seeded successfully!")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error seeding default data: {e}")

def get_database_status() -> Dict:
    """Get current database status"""
    try:
        # Test connection
        db.session.execute(text('SELECT 1'))
        
        # Count records
        status = {
            'status': 'healthy',
            'places': Place.query.count(),
            'track_types': TrackType.query.count(),
            'games': Game.query.count(),
            'players': Player.query.count(),
            'scores': Score.query.count(),
            'track_configurations': TrackConfiguration.query.count()
        }
        
        return status
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }

# ==========================================
# 🎯 HELPER FUNCTIONS
# ==========================================

def create_game(place_name: str, date_str: str, track_count: int, player_names: List[str]) -> Optional[Game]:
    """Create a new game with players"""
    try:
        # Get or create place
        place = Place.get_or_create(place_name, track_count)
        
        # Create game
        game_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        game = Game(
            place_id=place.id,
            place=place.name,
            date=game_date,
            track_count=track_count
        )
        db.session.add(game)
        db.session.flush()  # Get game ID
        
        # Create players
        for player_name in player_names:
            player = Player(game_id=game.id, name=player_name.strip())
            db.session.add(player)
        
        db.session.commit()
        return game
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating game: {e}")
        return None

def update_player_score(player_id: int, track_number: int, score_value: int) -> Tuple[bool, Dict[int, int]]:
    """Update player score and return success status + all player totals for the game"""
    try:
        player = Player.query.get(player_id)
        if not player:
            return False, {}
        
        # Update score
        success = player.set_score_for_track(track_number, score_value)
        if not success:
            return False, {}
        
        db.session.commit()
        
        # Get updated totals for all players in the game
        totals = {}
        for p in player.game.players:
            totals[p.id] = p.get_total_score()
        
        return True, totals
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating score: {e}")
        return False, {}

def get_game_with_data(game_id: int) -> Optional[Dict]:
    """Get game with all related data"""
    game = Game.query.get(game_id)
    if not game:
        return None
    
    return {
        'game': game.to_dict(include_players=True),
        'results': game.get_results(),
        'track_icons': game.get_track_icons(),
        'has_track_config': game.has_track_config
    }

# ==========================================
# 🔧 RENDER.COM CONFIGURATION
# ==========================================

def configure_for_render():
    """Configure database for Render.com deployment"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set!")
    
    # Fix postgres:// to postgresql:// for SQLAlchemy
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return {
        'SQLALCHEMY_DATABASE_URI': database_url,
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_timeout': 20,
            'max_overflow': 0,
        }
    }