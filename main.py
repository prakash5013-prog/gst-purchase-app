# main.py
from kivy.config import Config
Config.set("kivy", "log_enable", "0")
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.datatables import MDDataTable
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.list import ThreeLineIconListItem, IconLeftWidget
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.toast import toast
import os, sys, sqlite3, csv, time
from datetime import datetime, date
try:
    from plyer import filechooser
except Exception:
    filechooser = None
if platform == "android":
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    Uri = autoclass("android.net.Uri")
    Environment = autoclass("android.os.Environment")
    File = autoclass("java.io.File")
    MimeTypeMap = autoclass("android.webkit.MimeTypeMap")
else:
    PythonActivity = Intent = Uri = Environment = File = MimeTypeMap = None
APP_TITLE = "GST Purchase Report"
DB_FILE = "purchase_report.db"
PHOTO_DIR = "bill_photos"
EST_DIR = ".hidden_estimates"
KV = '''
<MToolbar@MDBoxLayout>:
    adaptive_height: True
    padding: dp(10), dp(8)
    spacing: dp(10)
    md_bg_color: app.theme_cls.bg_normal
    MDLabel:
        id: title_lbl
        text: app.toolbar_title
        bold: True
        font_style: "TitleMedium"
        on_touch_down: app._handle_title_taps(*args)
    MDRaisedButton:
        text: "Add Entry"
        on_release: app.open_entry_dialog()
    MDFlatButton:
        text: "Suppliers"
        on_release: app.open_suppliers()
    MDFlatButton:
        text: "Search"
        on_release: app.open_search()
    MDFlatButton:
        text: "Filter Supplier"
        on_release: app.open_filter_supplier()
    MDFlatButton:
        text: "Export CSV"
        on_release: app.export_csv()
    MDFlatButton:
        text: "Open Photo"
        on_release: app.open_selected_photo()
<TotalsBar@MDBoxLayout>:
    adaptive_height: True
    padding: dp(10), dp(8)
    spacing: dp(20)
    MDLabel:
        text: "Invoice Total: " + app.total_invoice
        font_style: "BodyMedium"
    MDLabel:
        text: "Tax Total: " + app.total_tax
        font_style: "BodyMedium"
    MDLabel:
        text: "Grand Total: " + app.total_grand
        font_style: "BodyMedium"
MDScreenManager:
    MDScreen:
        name: "main"
        MDBoxLayout:
            orientation: "vertical"
            MToolbar:
            MDCard:
                padding: dp(6)
                radius: dp(16)
                md_bg_color: app.theme_cls.backgroundColor
                MDBoxLayout:
                    id: table_holder
                    orientation: "vertical"
            TotalsBar:
'''
def ensure_dir(path: str):
    try: os.makedirs(path, exist_ok=True)
    except Exception: pass
def app_storage_dir():
    if hasattr(MDApp.get_running_app(), "user_data_dir"):
        return MDApp.get_running_app().user_data_dir
    return os.getcwd()
def abs_join(*parts): return os.path.abspath(os.path.join(*parts))
def guess_mime(path):
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if platform == "android" and MimeTypeMap:
        mtm = MimeTypeMap.getSingleton()
        mime = mtm.getMimeTypeFromExtension(ext)
        return mime if mime else "application/octet-stream"
    return {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","pdf":"application/pdf"}.get(ext,"application/octet-stream")
def open_with_default(path):
    if not os.path.exists(path): toast(f"File not found: {path}"); return
    if platform == "android":
        try:
            file = File(path); uri = Uri.fromFile(file); intent = Intent()
            intent.setAction(Intent.ACTION_VIEW); intent.setDataAndType(uri, guess_mime(path))
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            PythonActivity.mActivity.startActivity(intent)
        except Exception as e: toast(f"Open failed: {e}")
    else:
        if sys.platform.startswith("win"): os.startfile(path)
        elif sys.platform == "darwin": os.system(f'open "{path}"')
        else: os.system(f'xdg-open "{path}"')
def safe_copy_photo(src_path: str, bill_no: str, folder: str, suffix: str = ""):
    ensure_dir(folder); 
    if not src_path: return ""
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in (".jpg",".jpeg",".png",".pdf"): raise ValueError("Allowed: .jpg .jpeg .png .pdf")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized = "".join(c for c in (bill_no or "bill") if c.isalnum() or c in ("-","_"))
    dst = abs_join(folder, f"{sanitized}{suffix}_{ts}{ext}")
    with open(src_path,"rb") as fi, open(dst,"wb") as fo: fo.write(fi.read())
    return dst
class DB:
    def __init__(self, db_path):
        self._c = sqlite3.connect(db_path, check_same_thread=False)
        self._c.execute("PRAGMA foreign_keys=ON"); self._init()
    def _init(self):
        cu=self._c.cursor()
        cu.execute("CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE,gst TEXT)")
        cu.execute("CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY AUTOINCREMENT,bill_no TEXT,bill_date TEXT,supplier_id INTEGER,invoice REAL,tax_percent REAL,tax_amount REAL,total REAL,photo_path TEXT,estimate_photo_path TEXT,FOREIGN KEY(supplier_id) REFERENCES suppliers(id))")
        self._c.commit()
    def suppliers(self): return list(self._c.execute("SELECT id,name,gst FROM suppliers ORDER BY name"))
    def add_supplier(self,n,g): self._c.execute("INSERT INTO suppliers(name,gst) VALUES(?,?)",(n.strip(),g.strip())); self._c.commit()
    def edit_supplier(self,i,n,g): self._c.execute("UPDATE suppliers SET name=?,gst=? WHERE id=?", (n.strip(),g.strip(),i)); self._c.commit()
    def del_supplier(self,i): self._c.execute("DELETE FROM suppliers WHERE id=?", (i,)); self._c.commit()
    def supplier_id_by_name(self,n): r=self._c.execute("SELECT id FROM suppliers WHERE name=?", (n.strip(),)).fetchone(); return r[0] if r else None
    def supplier_gst_by_name(self,n): r=self._c.execute("SELECT gst FROM suppliers WHERE name=?", (n.strip(),)).fetchone(); return r[0] if r else ""
    def upsert_purchase(self,pid,bill_no,bill_date,supplier_name,invoice,taxp,tax,total,photo_path):
        sid=self.supplier_id_by_name(supplier_name); 
        if not sid: raise ValueError("Supplier not found")
        cu=self._c.cursor()
        if pid: cu.execute("UPDATE purchases SET bill_no=?,bill_date=?,supplier_id=?,invoice=?,tax_percent=?,tax_amount=?,total=?,photo_path=? WHERE id=?",(bill_no,bill_date,sid,invoice,taxp,tax,total,photo_path,pid))
        else: cu.execute("INSERT INTO purchases(bill_no,bill_date,supplier_id,invoice,tax_percent,tax_amount,total,photo_path) VALUES(?,?,?,?,?,?,?,?)",(bill_no,bill_date,sid,invoice,taxp,tax,total,photo_path))
        self._c.commit(); return cu.lastrowid if not pid else pid
    def set_estimate(self,pid,p): self._c.execute("UPDATE purchases SET estimate_photo_path=? WHERE id=?", (p,pid)); self._c.commit()
    def all(self,where=None,params=()):
        q=("SELECT p.id,p.bill_no,p.bill_date,s.name,s.gst,p.invoice,p.tax_percent,p.tax_amount,p.total,p.photo_path,p.estimate_photo_path "
           "FROM purchases p LEFT JOIN suppliers s ON p.supplier_id=s.id")
        if where: q+=" WHERE "+where
        q+=" ORDER BY p.bill_date DESC, p.id DESC"
        return list(self._c.execute(q,params))
    def with_est(self): return self.all("p.estimate_photo_path IS NOT NULL AND TRIM(p.estimate_photo_path)<>''")
class EstimateDialog(MDDialog):
    def __init__(self, app, pid, bill_no, cur, **kw):
        self.app=app; self.pid=pid; self.bill_no=bill_no; self.cur=cur or ""; self.sel=""
        self.f=MDTextField(text=os.path.basename(self.cur) if self.cur else "", readonly=True)
        super().__init__(title=f"Estimate (ID {pid})", type="custom",
                         content_cls=MDBoxLayout(orientation="vertical", spacing=dp(10),
                          children=[MDLabel(text=f"Bill No: {bill_no}", bold=True), self.f][::-1],
                          size_hint_y=None, height=dp(160)),
                         buttons=[MDFlatButton(text="Upload", on_release=self.pick),
                                  MDFlatButton(text="Open", on_release=self.open),
                                  MDFlatButton(text="Clear", on_release=self.clear),
                                  MDFlatButton(text="Close", on_release=lambda *_: self.dismiss()),
                                  MDRaisedButton(text="Save", on_release=self.save)], **kw)
    def pick(self,*_):
        if not filechooser: toast("No file chooser"); return
        def cb(sel):
            if sel: self.sel=sel[0]; self.f.text=os.path.basename(self.sel)
        filechooser.open_file(on_selection=cb, filters=[("Images/PDF", "*.jpg;*.jpeg;*.png;*.pdf")])
    def open(self,*_):
        p=self.sel or self.cur
        if not p: toast("No estimate file"); return
        open_with_default(p)
    def clear(self,*_): self.sel=""; self.cur=""; self.f.text=""
    def save(self,*_):
        try:
            root=app_storage_dir(); est_dir=abs_join(root, EST_DIR); ensure_dir(est_dir)
            path=self.cur or ""
            if self.sel: path=safe_copy_photo(self.sel, self.bill_no, est_dir, "_EST")
            self.app.db.set_estimate(self.pid, path)
            self.dismiss(); self.app.reload_table(); toast("Estimate saved")
        except Exception as e: toast(f"Save failed: {e}")
class EntryDialog(MDDialog):
    def __init__(self, app, pid=None, row=None, **kw):
        self.app=app; self.pid=pid
        self.sel=""; self.cur=row[9] if row else ""
        self.f_bill=MDTextField(text=row[1] if row else "", hint_text="Bill No")
        self.f_date=MDTextField(text=(row[2] if row else datetime.today().strftime("%Y-%m-%d")), hint_text="Bill Date (YYYY-MM-DD)")
        self.f_sup=MDTextField(text=row[3] if row else "", hint_text="Supplier (existing)")
        self.f_gst=MDTextField(text=row[4] if row else "", hint_text="GSTIN", readonly=True)
        self.f_inv=MDTextField(text=f"{row[5]:.2f}" if row else "", hint_text="Invoice Amount")
        self.f_taxp=MDTextField(text=f"{row[6]:.2f}" if row else "5", hint_text="Tax %")
        self.f_tax=MDTextField(text=f"{row[7]:.2f}" if row else "0.00", hint_text="Tax Amount", readonly=True)
        self.f_tot=MDTextField(text=f"{row[8]:.2f}" if row else "0.00", hint_text="Total Amount", readonly=True)
        self.f_photo=MDTextField(text=os.path.basename(self.cur) if self.cur else "", hint_text="Bill Photo (display only)", readonly=True)
        def recalc(*_):
            try: inv=float(self.f_inv.text or "0")
            except: inv=0.0
            try: p=float(self.f_taxp.text or "0")
            except: p=0.0
            tax=round(inv*p/100.0,2); tot=round(inv+tax,2); self.f_tax.text=f"{tax:.2f}"; self.f_tot.text=f"{tot:.2f}"
        self.f_inv.bind(text=recalc); self.f_taxp.bind(text=recalc)
        super().__init__(title="Purchase Entry", type="custom",
            content_cls=MDBoxLayout(orientation="vertical", spacing=dp(8),
                children=[self.f_tot,self.f_tax,self.f_taxp,self.f_inv,self.f_gst,self.f_sup,self.f_date,self.f_bill,self.f_photo][::-1],
                size_hint_y=None, height=dp(420)),
            buttons=[MDFlatButton(text="Upload Photo", on_release=self.pick),
                     MDFlatButton(text="Open Photo", on_release=self.open),
                     MDFlatButton(text="Clear Photo", on_release=self.clear),
                     MDFlatButton(text="Cancel", on_release=lambda *_: self.dismiss()),
                     MDRaisedButton(text="Save", on_release=self.save)], **kw)
        self.f_sup.bind(text=lambda *_: setattr(self.f_gst, "text", self.app.db.supplier_gst_by_name(self.f_sup.text.strip()) if self.f_sup.text.strip() else ""))
    def pick(self,*_):
        if not filechooser: toast("No file chooser"); return
        def cb(sel):
            if sel: self.sel=sel[0]; self.f_photo.text=os.path.basename(self.sel)
        filechooser.open_file(on_selection=cb, filters=[("Images/PDF","*.jpg;*.jpeg;*.png;*.pdf")])
    def open(self,*_):
        p=self.sel or self.cur
        if not p: toast("No photo"); return
        open_with_default(p)
    def clear(self,*_): self.sel=""; self.cur=""; self.f_photo.text=""
    def save(self,*_):
        try:
            datetime.strptime(self.f_date.text.strip(), "%Y-%m-%d")
        except Exception: toast("Date must be YYYY-MM-DD"); return
        bno=self.f_bill.text.strip(); sname=self.f_sup.text.strip()
        if not sname: toast("Supplier required"); return
        try:
            inv=float(self.f_inv.text or "0"); taxp=float(self.f_taxp.text or "0"); tax=float(self.f_tax.text or "0"); tot=float(self.f_tot.text or "0")
        except: toast("Invoice/Tax% must be numeric"); return
        root=app_storage_dir(); photo_dir=abs_join(root, PHOTO_DIR); ensure_dir(photo_dir); ensure_dir(abs_join(root, EST_DIR))
        photo_path=self.cur or ""
        if self.sel:
            try: photo_path=safe_copy_photo(self.sel, bno, photo_dir, "")
            except Exception as e: toast(f"Photo attach failed: {e}"); return
        try:
            self.app.db.upsert_purchase(self.pid,bno,self.f_date.text.strip(),sname,inv,taxp,tax,tot,photo_path)
            self.dismiss(); self.app.reload_table(); toast("Saved")
        except Exception as e: toast(str(e))
class PurchaseApp(MDApp):
    toolbar_title = "GST Purchase Report"
    total_invoice = "0.00"; total_tax="0.00"; total_grand="0.00"
    def build(self):
        root=Builder.load_string(KV)
        base=app_storage_dir(); ensure_dir(os.path.join(base, PHOTO_DIR)); ensure_dir(os.path.join(base, EST_DIR))
        self.db=DB(os.path.join(base, DB_FILE)); self._title_taps=[]
        Clock.schedule_once(lambda *_: self._init_table(root)); return root
    def _init_table(self, root):
        self.table_holder=root.get_screen("main").ids.table_holder
        self.table=MDDataTable(use_pagination=True, rows_num=12, column_data=[("ID",dp(40)),("Bill No",dp(120)),("Bill Date",dp(110)),("Supplier",dp(200)),("GSTIN",dp(140)),("Invoice",dp(100)),("Tax %",dp(70)),("Tax",dp(100)),("Total",dp(100)),("Photo",dp(70))], row_data=[], check=False)
        self.table.bind(on_row_press=self._row_press, on_row_long_press=self._row_long); self.table_holder.add_widget(self.table); self.reload_table()
    def reload_table(self, where=None, params=()):
        rows=self.db.all(where,params); data=[]; inv=tax=tot=0.0
        for r in rows:
            pid,bill_no,bill_date,sname,gst,invv,taxp,taxv,totv,photo,est=r
            data.append([str(pid),bill_no or "",bill_date or "",sname or "",gst or "",f"{invv:.2f}",f"{taxp:.2f}",f"{taxv:.2f}",f"{totv:.2f}","📷" if (photo or "") else ""])
            inv+=float(invv or 0); tax+=float(taxv or 0); tot+=float(totv or 0)
        self.total_invoice=f"{inv:.2f}"; self.total_tax=f"{tax:.2f}"; self.total_grand=f"{tot:.2f}"; self.table.row_data=data
    def _find(self,pid_str):
        try: pid=int(pid_str)
        except: return None
        rs=self.db.all("p.id=?", (pid,)); return rs[0] if rs else None
    def _row_press(self, table, cell):
        row=list(cell.table.row_data)[cell.table.row_controller.selected_row]; 
        if not row: return
        full=self._find(row[0]); 
        if not full: return
        sel=table.row_controller.current_selection
        if sel and sel[1]==9:
            p=full[9] or ""; open_with_default(p) if p else toast("No photo")
        else:
            EntryDialog(self, pid=int(row[0]), row=full).open()
    def _row_long(self, table, cell):
        row=list(cell.table.row_data)[cell.table.row_controller.selected_row]
        if not row: return
        full=self._find(row[0]); 
        if not full: return
        EstimateDialog(self, int(row[0]), full[1] or "", full[10] or "").open()
    def open_entry_dialog(self, pid=None, row=None):
        if pid and not row: row=self._find(str(pid))
        EntryDialog(self, pid=pid, row=row).open()
    def open_suppliers(self):
        items=self.db.suppliers()
        box=MDBoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None, height=dp(420))
        for sid,name,gst in items:
            it=ThreeLineIconListItem(text=name, secondary_text=gst or "", tertiary_text=f"ID: {sid}")
            it.add_widget(IconLeftWidget(icon="account"))
            box.add_widget(it)
        dlg=MDDialog(title="Suppliers", type="custom", content_cls=box, buttons=[MDFlatButton(text="Close", on_release=lambda *_: dlg.dismiss()), MDRaisedButton(text="Add Supplier", on_release=lambda *_: MDDialog(title="New Supplier", type="custom", content_cls=MDBoxLayout(orientation="vertical", children=[MDTextField(hint_text='Name', id='n'), MDTextField(hint_text='GSTIN', id='g')]), buttons=[MDFlatButton(text='Cancel', on_release=lambda *_: dlg.dismiss())]).open())])
        dlg.open()
    def open_search(self):
        d1=MDTextField(text=date.today().replace(day=1).strftime("%Y-%m-%d"), hint_text="From YYYY-MM-DD")
        d2=MDTextField(text=date.today().strftime("%Y-%m-%d"), hint_text="To YYYY-MM-DD")
        dlg=MDDialog(title="Search (Date Range)", type="custom", content_cls=MDBoxLayout(orientation="vertical", spacing=dp(8), children=[d2,d1][::-1], size_hint_y=None, height=dp(160)), buttons=[MDFlatButton(text="Cancel", on_release=lambda *_: dlg.dismiss()), MDRaisedButton(text="Search", on_release=lambda *_: (dlg.dismiss(), self.reload_table("p.bill_date BETWEEN ? AND ?", (d1.text, d2.text))))]); dlg.open()
    def open_filter_supplier(self):
        tf=MDTextField(hint_text="Supplier name (contains)")
        dlg=MDDialog(title="Filter Supplier", type="custom", content_cls=MDBoxLayout(orientation="vertical", spacing=dp(8), children=[tf], size_hint_y=None, height=dp(100)), buttons=[MDFlatButton(text="Close", on_release=lambda *_: dlg.dismiss()), MDRaisedButton(text="Search", on_release=lambda *_: (dlg.dismiss(), self.reload_table("s.name LIKE ?", (f"%{tf.text.strip()}%",))))]); dlg.open()
    def open_selected_photo(self):
        try: idx=self.table.row_controller.selected_row
        except Exception: toast("Select a row"); return
        if idx is None: toast("Select a row"); return
        full=self._find(self.table.row_data[idx][0])
        if full and full[9]: open_with_default(full[9])
        else: toast("No photo")
    def export_csv(self):
        rows=self.table.row_data
        if not rows: toast("Nothing to export"); return
        try:
            if platform=="android":
                downloads=Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).getAbsolutePath()
            else:
                downloads=os.getcwd()
            os.makedirs(downloads, exist_ok=True)
            path=os.path.join(downloads, f"purchase_export_{int(time.time())}.csv")
            with open(path,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(["Bill No","Bill Date","Supplier","GSTIN","Invoice","Tax %","Tax Amt","Total"])
                inv=tax=tot=0.0
                for r in rows:
                    w.writerow([r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8]])
                    try: inv+=float(r[5]); tax+=float(r[7]); tot+=float(r[8])
                    except: pass
                w.writerow([]); w.writerow(["TOTAL","","","",f"{inv:.2f}","",f"{tax:.2f}",f"{tot:.2f}"])
            toast(f"Saved: {path}")
        except Exception as e: toast(f"Export failed: {e}")
    def _handle_title_taps(self, widget, touch):
        if not widget.collide_point(*touch.pos): return
        now=time.time(); taps=getattr(self,"_title_taps",[]); self._title_taps=[t for t in taps if now-t<1.5]+[now]
        if len(self._title_taps)>=5: self._title_taps.clear(); MDDialog(title="Estimate Browser (Hidden)", text="Implement list...", buttons=[MDFlatButton(text="Close", on_release=lambda *_: None)]).open()
if __name__ == "__main__":
    PurchaseApp().run()
