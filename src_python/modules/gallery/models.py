"""
Modelos SQLAlchemy para el módulo Gallery.
Incluye jerarquía persistida de subcarpetas y tags por nodo.
"""

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    Table,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ...shared.database import Base


folder_node_tags = Table(
    "folder_node_tags",
    Base.metadata,
    Column("folder_node_id", BigInteger, ForeignKey("folder_nodes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", BigInteger, ForeignKey("folder_tags.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Text, primary_key=True)
    path = Column(Text, nullable=False, unique=True, index=True)
    name = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    last_scan_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    images = relationship("Image", back_populates="folder", cascade="all, delete-orphan")
    nodes = relationship("FolderNode", back_populates="folder_root", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Folder(id='{self.id}', path='{self.path}', name='{self.name}')>"


class FolderNode(Base):
    __tablename__ = "folder_nodes"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    folder_root_id = Column(Text, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_node_id = Column(BigInteger, ForeignKey("folder_nodes.id", ondelete="CASCADE"), nullable=True, index=True)
    rel_path = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    depth = Column(Integer, nullable=False, default=0)
    naming_base = Column(Text, nullable=True)
    naming_number_width = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("folder_root_id", "rel_path", name="uq_folder_nodes_root_rel_path"),
    )

    folder_root = relationship("Folder", back_populates="nodes")
    parent = relationship("FolderNode", remote_side=[id], back_populates="children")
    children = relationship("FolderNode", back_populates="parent", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="folder_node")
    tags = relationship("FolderTag", secondary=folder_node_tags, back_populates="nodes")


class FolderTag(Base):
    __tablename__ = "folder_tags"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True, index=True)
    color = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    nodes = relationship("FolderNode", secondary=folder_node_tags, back_populates="tags")


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    folder_id = Column(Text, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_node_id = Column(BigInteger, ForeignKey("folder_nodes.id", ondelete="SET NULL"), nullable=True, index=True)

    path = Column(Text, nullable=False)
    thumb_path = Column(Text, nullable=True)
    size = Column(BigInteger, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    guid = Column(String(36), nullable=True, unique=True, index=True)
    prompt_json = Column(JSONB, nullable=True)
    workflow_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("folder_id", "path", name="uq_images_folder_path"),
    )

    folder = relationship("Folder", back_populates="images")
    folder_node = relationship("FolderNode", back_populates="images")

    def __repr__(self):
        return f"<Image(id={self.id}, guid='{self.guid}', folder_id='{self.folder_id}', path='{self.path}')>"


