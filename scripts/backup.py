"""Offline or online local SQLite backup. Usage: python scripts/backup.py source destination"""
import argparse
import sqlite3
from pathlib import Path

p=argparse.ArgumentParser(description='使用 SQLite backup API 生成一致性备份')
p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
a=p.parse_args()
if not a.source.is_file() or a.destination.exists():
    p.error('源数据库必须存在；目标文件不能已存在')
src=sqlite3.connect(a.source.resolve().as_uri()+'?mode=ro',uri=True)
dst=sqlite3.connect(a.destination)
try:
    src.backup(dst)
    assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
finally:
    src.close();dst.close()
print('备份完成：'+str(a.destination.resolve()))
