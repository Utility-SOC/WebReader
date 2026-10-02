"""
Admin CLI for the library. Deliberately not an HTTP API: there is nothing for an
anonymous visitor to reach.

  python -m backend.library_cli add-source NAME --root /data/docs --include 'public/**' [--exclude 'public/drafts/**']
        [--rule 'planning/=Planning Commission:zoning,land use'] [--no-hold]
  python -m backend.library_cli sources
  python -m backend.library_cli sync NAME [--dry-run] [--no-process]
  python -m backend.library_cli held NAME              # what is waiting for release
  python -m backend.library_cli release NAME [--path P ...]
  python -m backend.library_cli withdraw NAME --path P ...
  python -m backend.library_cli search "water rights" [--all]
"""

import argparse
import json
import sys

from . import search
from .database import Base, SessionLocal, engine
from .ingest import release, sync_source, withdraw
from .library_models import Item, ItemStatus, Source


def _db():
    from . import library_models  # noqa: F401  (register tables)
    Base.metadata.create_all(bind=engine)
    search.ensure_schema(engine)
    return SessionLocal()


def _source(db, name):
    s = db.query(Source).filter(Source.name == name).first()
    if not s:
        sys.exit(f"No source named '{name}'. See: sources")
    return s


def _rule(text):
    prefix, _, rest = text.partition("=")
    agency, _, tags = rest.partition(":")
    return {"prefix": prefix.strip(), "agency": agency.strip() or None, "tags": [t.strip() for t in tags.split(",") if t.strip()]}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="library_cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-source"); a.add_argument("name"); a.add_argument("--kind", default="folder"); a.add_argument("--root", required=True)
    a.add_argument("--include", action="append", default=[]); a.add_argument("--exclude", action="append", default=[])
    a.add_argument("--rule", action="append", default=[]); a.add_argument("--no-hold", action="store_true")
    sub.add_parser("sources")
    s = sub.add_parser("sync"); s.add_argument("name"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--no-process", action="store_true")
    h = sub.add_parser("held"); h.add_argument("name")
    r = sub.add_parser("release"); r.add_argument("name"); r.add_argument("--path", action="append")
    w = sub.add_parser("withdraw"); w.add_argument("name"); w.add_argument("--path", action="append", required=True)
    q = sub.add_parser("search"); q.add_argument("query"); q.add_argument("--all", action="store_true", help="include held items")
    args = ap.parse_args(argv)

    db = _db()
    if args.cmd == "add-source":
        if not args.include:
            sys.exit("Refusing to add a source with no --include pattern: nothing would be published. "
                     "Use --include 'public/**' to publish a folder, or --include '**' to allow everything.")
        db.add(Source(name=args.name, kind=args.kind, config={"root": args.root}, include=args.include, exclude=args.exclude,
                      hold_new=not args.no_hold, path_rules=[_rule(x) for x in args.rule]))
        db.commit()
        print(f"Added source '{args.name}'. New items will be {'held for release' if not args.no_hold else 'published immediately'}.")
    elif args.cmd == "sources":
        for src in db.query(Source).all():
            n = db.query(Item).filter(Item.source_id == src.id).count()
            print(f"{src.name}: {src.kind} {src.config} include={src.include} exclude={src.exclude} hold_new={src.hold_new} items={n}")
    elif args.cmd == "sync":
        rep = sync_source(db, _source(db, args.name), dry_run=args.dry_run, process=not args.no_process)
        print(("DRY RUN (nothing changed): " if args.dry_run else "") + json.dumps(rep.summary()))
        if args.dry_run:
            for p in rep.new: print("  would add    ", p)
            for p in rep.changed: print("  would update ", p)
            for p in rep.removed: print("  would remove ", p)
        for p, err in rep.failed: print("  FAILED", p, err)
    elif args.cmd == "held":
        src = _source(db, args.name)
        for it in db.query(Item).filter(Item.source_id == src.id, Item.status == ItemStatus.READY.value, Item.visible.is_(False)):
            print(f"{it.path}  ({it.file_type})  {it.title}")
    elif args.cmd == "release":
        print(f"Released {release(db, _source(db, args.name), args.path)} item(s).")
    elif args.cmd == "withdraw":
        print(f"Withdrew {withdraw(db, _source(db, args.name), args.path)} item(s).")
    elif args.cmd == "search":
        res = search.search(db, args.query, include_hidden=args.all)
        print(f"{res['total']} result(s)")
        for r_ in res["results"]:
            print(f"  [{r_['id']}] {r_['title']}  ({r_['file_type']}, {r_['agency'] or 'no agency'})  {r_['snippet'] or ''}")


if __name__ == "__main__":
    main()
