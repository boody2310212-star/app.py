import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import requests
import json
import plotly.express as px
from datetime import datetime, timedelta
import io

st.set_page_config(page_title="EpiPredict + ICD-11 Pro - جميع امراض العالم", page_icon="☣️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap');
    * { font-family: 'Tajawal', sans-serif !important; direction: rtl; }
    .main-header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); padding: 2rem; border-radius: 16px; margin-bottom: 1.5rem; text-align: center; border: 1px solid rgba(255,255,255,0.1); }
    .main-header h1 { color: #e94560; font-weight: 900; font-size: 2.5rem; margin: 0; }
    .main-header p { color: #a0a0a0; font-size: 1.1rem; margin-top: 0.5rem; }
    .metric-card { background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%); border-radius: 12px; padding: 1.2rem; border: 1px solid rgba(233,69,96,0.2); text-align: center; transition: transform 0.3s; }
    .metric-card:hover { transform: translateY(-3px); border-color: #e94560; }
    .emergency-banner { background: linear-gradient(90deg, #e94560 0%, #ff6b6b 100%); color: white; padding: 1rem 2rem; border-radius: 12px; text-align: center; font-weight: 700; font-size: 1.1rem; animation: pulse 2s infinite; margin-bottom: 1rem; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.8; } }
    .disease-card { background: #16213e; border-radius: 12px; padding: 1rem; margin-bottom: 0.8rem; border-right: 4px solid #e94560; transition: all 0.3s; }
    .disease-card:hover { background: #1a1a2e; transform: translateX(-5px); }
    .chat-message { padding: 0.8rem 1rem; border-radius: 12px; margin-bottom: 0.5rem; max-width: 80%; }
    .chat-user { background: #e94560; color: white; margin-right: auto; border-bottom-left-radius: 4px; }
    .chat-bot { background: #16213e; color: #e0e0e0; border-bottom-right-radius: 4px; }
    .sync-log-item { background: #0a0a0a; border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 0.4rem; border-right: 3px solid #0f3460; font-size: 0.85rem; }
    .sync-log-item.success { border-right-color: #00d9ff; }
    .sync-log-item.error { border-right-color: #e94560; }
    .sync-log-item.warning { border-right-color: #ffd700; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: #16213e; padding: 0.5rem; border-radius: 12px; }
    .stTabs [data-baseweb="tab"] { background: transparent; border-radius: 8px; color: #a0a0a0; font-weight: 600; padding: 0.6rem 1.2rem; }
    .stTabs [aria-selected="true"] { background: #e94560 !important; color: white !important; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #0a0a0a; }
    ::-webkit-scrollbar-thumb { background: #e94560; border-radius: 3px; }
    @media (max-width: 768px) { .main-header h1 { font-size: 1.5rem; } .metric-card { padding: 0.8rem; } }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>☣️ EpiPredict + ICD-11 Pro</h1>
    <p>جميع امراض العالم | 55,000+ مرض من WHO ICD-11 API | AI-Powered</p>
</div>
""", unsafe_allow_html=True)

ICD_TOKEN_ENDPOINT = "https://icdaccessmanagement.who.int/connect/token"
ICD_API_BASE = "https://id.who.int"

default_sessions = {
    'icd_credentials': {'client_id': '', 'client_secret': '', 'token': None, 'token_expiry': None},
    'icd_search_results': [],
    'all_icd_diseases': [],
    'diseases_db': {},
    'map_data': pd.DataFrame({'lat': [], 'lon': [], 'risk_score': [], 'disease_name': []}),
    'sync_log': [],
    'chat_history': [],
    'webhook_url': '',
    'webhook_enabled': False,
    'language': 'ar',
    'last_sync': None,
    'export_history': [],
}
for key, value in default_sessions.items():
    if key not in st.session_state:
        st.session_state[key] = value

def add_sync_log(message, status="info"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state['sync_log'].insert(0, {'timestamp': timestamp, 'message': message, 'status': status})
    if len(st.session_state['sync_log']) > 50:
        st.session_state['sync_log'] = st.session_state['sync_log'][:50]

def get_icd_token():
    creds = st.session_state['icd_credentials']
    if creds['token'] and creds['token_expiry'] and datetime.now() < creds['token_expiry']:
        return creds['token']
    if not creds['client_id'] or not creds['client_secret']:
        return None
    payload = {'client_id': creds['client_id'], 'client_secret': creds['client_secret'], 'scope': 'icdapi_access', 'grant_type': 'client_credentials'}
    try:
        response = requests.post(ICD_TOKEN_ENDPOINT, data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)
        st.session_state['icd_credentials']['token'] = token
        st.session_state['icd_credentials']['token_expiry'] = datetime.now() + timedelta(seconds=expires_in - 60)
        add_sync_log("تم تجديد التوكن بنجاح", "success")
        return token
    except Exception as e:
        add_sync_log(f"فشل المصادقة: {str(e)[:50]}", "error")
        return None

def search_icd11(query, language="ar", max_results=50):
    token = get_icd_token()
    if not token: return None
    search_url = f"{ICD_API_BASE}/icd/entity/search"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'Accept-Language': language, 'API-Version': 'v2'}
    params = {'q': query, 'useFlexisearch': 'true', 'flatResults': 'true', 'highlightingEnabled': 'true'}
    try:
        response = requests.get(search_url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        add_sync_log(f"خطأ في البحث: {str(e)[:50]}", "error")
        return None

def get_icd_entity(uri, language="ar"):
    token = get_icd_token()
    if not token: return None
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'Accept-Language': language, 'API-Version': 'v2'}
    try:
        secure_uri = uri.replace("http://", "https://")
        response = requests.get(secure_uri, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except: return None

def get_icd_children(uri, language="ar"):
    token = get_icd_token()
    if not token: return None
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'Accept-Language': language, 'API-Version': 'v2'}
    try:
        secure_uri = uri.replace("http://", "https://")
        response = requests.get(f"{secure_uri}/child", headers=headers, timeout=10)
        if response.status_code == 200: return response.json()
        return None
    except: return None

def get_icd_linearization(entity_id, linearization="mms", language="ar"):
    token = get_icd_token()
    if not token: return None
    url = f"{ICD_API_BASE}/icd/release/11/2025-01/{linearization}/{entity_id}"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'Accept-Language': language, 'API-Version': 'v2'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200: return response.json()
        return None
    except: return None

def fetch_all_icd_diseases(language="ar"):
    token = get_icd_token()
    if not token: return []
    search_terms = ["infectious", "neoplasm", "blood", "endocrine", "mental", "nervous", "eye", "ear", "circulatory", "respiratory", "digestive", "skin", "musculoskeletal", "genitourinary", "pregnancy", "perinatal", "congenital", "symptom", "injury", "poisoning", "external", "health", "factor", "bacterial", "viral", "fungal", "parasitic", "cancer", "tumor", "diabetes", "heart", "lung", "liver", "kidney", "brain", "bone", "العدوى", "السرطان", "القلب", "السكري", "الرئة", "الكبد", "الكلى"]
    all_results = []
    seen_ids = set()
    for term in search_terms:
        try:
            results = search_icd11(term, language=language, max_results=50)
            if results and 'destinationEntities' in results:
                for entity in results['destinationEntities']:
                    entity_id = entity.get('id', '')
                    if entity_id and entity_id not in seen_ids:
                        seen_ids.add(entity_id)
                        all_results.append({'id': entity_id, 'title': entity.get('title', 'غير معروف'), 'definition': entity.get('definition', 'لا يوجد تعريف'), 'theCode': entity.get('theCode', '---'), 'score': entity.get('score', 0), 'uri': f"http://id.who.int/icd/entity/{entity_id.split('/')[-1]}" if entity_id else None})
        except Exception as e:
            add_sync_log(f"خطأ في جلب '{term}': {str(e)[:30]}", "error")
            continue
    add_sync_log(f"تم جلب {len(all_results)} مرض فريد من ICD-11", "success")
    return all_results

def ai_classify_disease(disease_info):
    symptoms = " ".join(disease_info.get('symptoms', [])).lower()
    category = disease_info.get('category', '').lower()
    risk = disease_info.get('risk_level', '').lower()
    classification = {'severity': 'غير محدد', 'severity_color': '#808080', 'type': 'غير محدد', 'icd_chapter': 'غير محدد', 'priority': 0}
    if any(x in risk for x in ['مرتفع جدا', 'طوارئ', 'وبائي']): classification.update({'severity': 'حرج', 'severity_color': '#e94560', 'priority': 5})
    elif 'مرتفع' in risk: classification.update({'severity': 'عالي', 'severity_color': '#ff6b6b', 'priority': 4})
    elif 'متوسط' in risk: classification.update({'severity': 'متوسط', 'severity_color': '#ffd700', 'priority': 3})
    else: classification.update({'severity': 'منخفض', 'severity_color': '#00d9ff', 'priority': 2})
    if any(x in category for x in ['بكتيري', 'bacterial', 'عدوى']): classification.update({'type': 'عدوى بكتيرية', 'icd_chapter': 'الامراض المعدية (الفصل 1)'})
    elif any(x in category for x in ['فيروسي', 'viral']): classification.update({'type': 'عدوى فيروسية', 'icd_chapter': 'الامراض المعدية (الفصل 1)'})
    elif any(x in category for x in ['سرطان', 'cancer', 'اورام', 'neoplasm']): classification.update({'type': 'اورام خبيثة', 'icd_chapter': 'الاورام (الفصل 2)'})
    elif any(x in category for x in ['نزفي', 'hemorrhagic', 'blood']): classification.update({'type': 'امراض الدم', 'icd_chapter': 'امراض الدم (الفصل 3)'})
    elif any(x in category for x in ['قلب', 'heart', 'circulatory']): classification.update({'type': 'امراض القلب', 'icd_chapter': 'القلب والدورة الدموية (الفصل 11)'})
    elif any(x in category for x in ['سكري', 'diabetes', 'endocrine']): classification.update({'type': 'امراض الغدد', 'icd_chapter': 'الغدد الصماء (الفصل 5)'})
    elif any(x in category for x in ['رئة', 'lung', 'respiratory']): classification.update({'type': 'امراض التنفس', 'icd_chapter': 'التنفس (الفصل 12)'})
    else: classification.update({'type': 'حالة طبية عامة', 'icd_chapter': 'فصول متنوعة'})
    return classification

def send_webhook_alert(disease_name, risk_level, status):
    if not st.session_state.get('webhook_enabled') or not st.session_state.get('webhook_url'): return False
    payload = {"timestamp": datetime.now().isoformat(), "alert_type": "disease_emergency", "disease_name": disease_name, "risk_level": risk_level, "status": status, "source": "EpiPredict Pro", "priority": "HIGH" if "طوارئ" in status or "🚨" in status else "MEDIUM"}
    try:
        response = requests.post(st.session_state['webhook_url'], json=payload, timeout=5, headers={"Content-Type": "application/json"})
        add_sync_log(f"Webhook sent: {disease_name}", "success")
        return response.status_code == 200
    except Exception as e:
        add_sync_log(f"Webhook failed: {str(e)[:50]}", "error")
        return False

def export_to_csv():
    data = []
    for name, info in st.session_state['diseases_db'].items():
        classification = ai_classify_disease(info)
        data.append({'اسم المرض': name, 'التصنيف': info.get('category', ''), 'الاعراض': ' | '.join(info.get('symptoms', [])), 'الحالة': info.get('status', ''), 'البروتوكول': info.get('treatment', ''), 'مستوى الخطر': info.get('risk_level', ''), 'كود ICD-11': info.get('icd11_code', ''), 'شدة AI': classification['severity'], 'نوع AI': classification['type'], 'فصل ICD': classification['icd_chapter'], 'تاريخ الاضافة': info.get('added_date', datetime.now().strftime("%Y-%m-%d"))})
    df = pd.DataFrame(data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"EpiPredict_Export_{timestamp}.csv"
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    st.session_state['export_history'].append({'filename': filename, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'records': len(data)})
    add_sync_log(f"تصدير CSV: {len(data)} سجل", "success")
    return csv, filename

def export_to_excel():
    data = []
    for name, info in st.session_state['diseases_db'].items():
        classification = ai_classify_disease(info)
        data.append({'اسم المرض': name, 'التصنيف': info.get('category', ''), 'الاعراض': ' | '.join(info.get('symptoms', [])), 'الحالة': info.get('status', ''), 'البروتوكول': info.get('treatment', ''), 'مستوى الخطر': info.get('risk_level', ''), 'كود ICD-11': info.get('icd11_code', ''), 'شدة AI': classification['severity'], 'نوع AI': classification['type'], 'فصل ICD': classification['icd_chapter'], 'تاريخ الاضافة': info.get('added_date', datetime.now().strftime("%Y-%m-%d"))})
    df = pd.DataFrame(data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"EpiPredict_Export_{timestamp}.xlsx"
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Diseases', index=False)
        stats = pd.DataFrame({'المؤشر': ['اجمالي الامراض', 'مرتبطة بـ ICD-11', 'حالات طوارئ', 'بكتيرية', 'فيروسية', 'اورام'], 'القيمة': [len(st.session_state['diseases_db']), sum(1 for d in st.session_state['diseases_db'].values() if d.get('icd11_code')), sum(1 for d in st.session_state['diseases_db'].values() if "طوارئ" in d.get('status', '')), sum(1 for d in st.session_state['diseases_db'].values() if 'بكتيري' in d.get('category', '')), sum(1 for d in st.session_state['diseases_db'].values() if 'فيروسي' in d.get('category', '')), sum(1 for d in st.session_state['diseases_db'].values() if 'سرطان' in d.get('category', ''))]})
        stats.to_excel(writer, sheet_name='Statistics', index=False)
    st.session_state['export_history'].append({'filename': filename, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'records': len(data)})
    add_sync_log(f"تصدير Excel: {len(data)} سجل", "success")
    return output.getvalue(), filename

def chatbot_response(user_message):
    msg_lower = user_message.lower()
    responses = {'مرحبا': 'مرحباً بك في EpiPredict Pro! انا مساعدك الطبي الذكي. كيف يمكنني مساعدتك؟', 'طاعون': 'الطاعون (Plague) هو مرض بكتيري خطير يسببه Yersinia pestis. كود ICD-11: 1B93', 'ايبولا': 'فيروس ايبولا هو مرض نزفي حاد. كود ICD-11: 1D60.3', 'كوفيد': 'COVID-19 هو فيروس تنفسي. كود ICD-11: RA01.0', 'كوليرا': 'الكوليرا تسبب اسهالاً مائياً حاداً. كود ICD-11: 1A00', 'سكري': 'السكري (Diabetes) هو اضطراب استقلابي. كود ICD-11: 5A11', 'قلب': 'امراض القلب تشمل عدة حالات. ابحث في ICD-11 للحصول على التفاصيل الدقيقة.', 'سرطان': 'السرطان (Cancer) هو نمو غير طبيعي للخلايا. ICD-11 يحتوي على اكثر من 1000 كود لانواع مختلفة.', 'icd': 'ICD-11 هو التصنيف الدولي للامراض من WHO. يحتوي على اكثر من 55,000 كود.', 'مساعدة': 'يمكنني مساعدتك في: البحث عن امراض وكودات ICD-11، شرح الاعراض والعلاجات.'}
    for key, response in responses.items():
        if key in msg_lower: return response
    if '?' in user_message or '؟' in user_message: return f"سؤال ممتاز! بخصوص '{user_message[:30]}...' - يمكنك البحث في ICD-11 من الشريط الجانبي."
    return f"شكراً لمشاركتك. يمكنني مساعدتك في البحث عن '{user_message[:20]}' في قاعدة بيانات ICD-11 العالمية."

if not st.session_state['diseases_db']:
    st.session_state['diseases_db'] = {"مرض الطاعون (Plague - Yersinia pestis)": {"category": "بكتيري شديد الخطورة / طوارئ", "symptoms": ["تضخم مؤلم جداً للغدد الليمفاوية", "حمى مفاجئة وشديدة", "سعال مصحوب بدم", "قشعريرة وضيق تنفس"], "status": "طوارئ عالمية / طاعون 🚨", "treatment": "المضادات الحيوية الفورية مثل (Streptomycin / Doxycycline) والعزل الصحي.", "risk_level": "مرتفع جداً (حالة طوارئ)", "icd11_code": "1B93", "icd11_uri": "http://id.who.int/icd/entity/257068234", "added_date": "2025-01-15"}, "فيروس ايبولا (Ebola Virus)": {"category": "فيروسي نزفي / شديد الفتك", "symptoms": ["نزيف داخلي وخارجي", "حمى حادة مفاجئة", "اسهال وقيء شديد", "ضعف وآلام مفاصل حادة"], "status": "طوارئ وبائية 🚨", "treatment": "الاجسام المضادة الموجهة (Inmazeb / Ebanga)، تعويض السوائل والدم.", "risk_level": "مرتفع جداً", "icd11_code": "1D60.3", "icd11_uri": "http://id.who.int/icd/entity/1585297628", "added_date": "2025-01-15"}, "كوفيد-19 (Covid-19)": {"category": "فيروسي / تنفسي", "symptoms": ["حمى", "سعال جاف", "فقدان الشم والتذوق", "ضيق تنفس"], "status": "تحت المراقبة 🟡", "treatment": "الراحة التامة، ومضادات الفيروسات المعتمدة.", "risk_level": "متوسط", "icd11_code": "RA01.0", "icd11_uri": "http://id.who.int/icd/entity/1630407678", "added_date": "2025-01-15"}, "الكوليرا (Cholera)": {"category": "بكتيري / معوي", "symptoms": ["اسهال مائي حاد", "جفاف شديد", "قيء"], "status": "تحذير مناطقي 🟠", "treatment": "محلول اعادة الارواء (ORS)، املاح وريدية، ومضادات حيوية.", "risk_level": "مرتفع", "icd11_code": "1A00", "icd11_uri": "http://id.who.int/icd/entity/257068234", "added_date": "2025-01-15"}, "سرطان الثدي (Breast Cancer)": {"category": "اورام خبيثة / سرطان", "symptoms": ["كتلة غير مؤلمة بالثدي", "تغيرات في الجلد", "تضخم العقد الليمفاوية"], "status": "مرض مزمن / علاج متاح 🟡", "treatment": "العلاج الكيميائي، الاشعاعي، الجراحي، والهرموني.", "risk_level": "مرتفع", "icd11_code": "2C6Y", "icd11_uri": "http://id.who.int/icd/entity/1630407678", "added_date": "2025-01-15"}, "السكري (Diabetes Mellitus)": {"category": "غدد صماء / استقلابي", "symptoms": ["عطش شديد", "تبول متكرر", "ارهاق", "ضبابية الرؤية", "تأخر التئام الجروح"], "status": "مرض مزمن / علاج متاح 🟡", "treatment": "الانسولين، ادوية خفض السكر، نظام غذائي، وممارسة رياضية.", "risk_level": "مرتفع", "icd11_code": "5A11", "icd11_uri": "http://id.who.int/icd/entity/466350573", "added_date": "2025-01-15"}, "امراض القلب الاقفارية (Ischemic Heart Disease)": {"category": "قلب ودورة دموية", "symptoms": ["ألم صدرية", "ضيق تنفس", "تعرق", "غثيان", "ألم في الذراع اليسرى"], "status": "مرض مزمن / علاج متاح 🟡", "treatment": "الاسبرين، ادوية خفض الكوليسترول، قسطرة، جراحة القلب المفتوح.", "risk_level": "مرتفع", "icd11_code": "BA40", "icd11_uri": "http://id.who.int/icd/entity/1435254666", "added_date": "2025-01-15"}, "الملاريا (Malaria)": {"category": "طفيلي / منقول بالبعوض", "symptoms": ["حمى متقطعة", "قشعريرة", "تعرق", "انيميا", "تضخم الطحال"], "status": "تحت المراقبة 🟡", "treatment": "ادوية مضادة للملاريا (Artemisinin-based Combination Therapy).", "risk_level": "مرتفع", "icd11_code": "1F40", "icd11_uri": "http://id.who.int/icd/entity/257068234", "added_date": "2025-02-01"}}

if st.session_state['map_data'].empty:
    st.session_state['map_data'] = pd.DataFrame({'lat': [30.0444, 31.2001, 29.9870, 30.5852, 25.6872, 24.0889, 26.8206], 'lon': [31.2357, 29.9187, 31.1421, 31.5048, 32.6396, 32.8998, 30.8025], 'risk_score': [95, 60, 80, 90, 75, 85, 70], 'disease_name': ['الطاعون', 'كوفيد-19', 'الكوليرا', 'ايبولا', 'حمى الضنك', 'الملاريا', 'سرطان الثدي']})

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:1rem; background:linear-gradient(135deg, #1a1a2e, #16213e); border-radius:12px; margin-bottom:1rem; border:1px solid rgba(233,69,96,0.3);">
        <h3 style="color:#e94560; margin:0;">☣️ EpiPredict Pro</h3>
        <p style="color:#a0a0a0; font-size:0.8rem; margin:0.3rem 0 0 0;">v8.0 | WHO ICD-11 API | 55,000+ مرض</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🔐 اعدادات ICD-11 API", expanded=True):
        st.info("""
        **خطوات التسجيل:**
        1. زُر [icd.who.int/icdapi](https://icd.who.int/icdapi)
        2. انشئ حساباً
        3. احصل على Client ID & Secret
        """)
        client_id = st.text_input("Client ID:", value=st.session_state['icd_credentials']['client_id'], type="password", key="client_id_input")
        client_secret = st.text_input("Client Secret:", value=st.session_state['icd_credentials']['client_secret'], type="password", key="client_secret_input")
        col_test1, col_test2 = st.columns(2)
        with col_test1:
            if st.button("💾 حفظ", use_container_width=True):
                st.session_state['icd_credentials']['client_id'] = client_id
                st.session_state['icd_credentials']['client_secret'] = client_secret
                st.session_state['icd_credentials']['token'] = None
                add_sync_log("تم حفظ بيانات الاعتماد", "info")
                st.success("✅ تم الحفظ!")
                st.rerun()
        with col_test2:
            if st.button("🔗 اختبار", use_container_width=True):
                st.session_state['icd_credentials']['client_id'] = client_id
                st.session_state['icd_credentials']['client_secret'] = client_secret
                st.session_state['icd_credentials']['token'] = None
                token = get_icd_token()
                if token: st.success("🎉 الاتصال ناجح!")
                else: st.error("❌ فشل الاتصال")

    st.divider()

    with st.expander("🔍 البحث في ICD-11 العالمي (55,000+ مرض)", expanded=True):
        icd_language = st.selectbox("لغة البحث:", [("🇦🇪 العربية", "ar"), ("🇬🇧 English", "en")], format_func=lambda x: x[0])[1]
        icd_query = st.text_input("ابحث عن اي مرض في العالم:", placeholder="مثال: diabetes, سرطان, plague, سكري...", key="icd_search_input")
        if st.button("🔎 بحث في ICD-11", type="primary", use_container_width=True):
            if not client_id or not client_secret: st.error("❌ ادخل بيانات الاعتماد اولاً!")
            elif not icd_query.strip(): st.warning("⚠️ ادخل نص البحث")
            else:
                with st.spinner("جاري البحث في 55,000+ مرض من WHO..."):
                    results = search_icd11(icd_query, language=icd_language)
                    if results:
                        st.session_state['icd_search_results'] = results.get('destinationEntities', [])
                        count = len(st.session_state['icd_search_results'])
                        add_sync_log(f"بحث ICD-11: '{icd_query}' - {count} نتيجة", "success")
                        st.success(f"✅ تم العثور على {count} مرض!")
                    else: st.error("❌ لا توجد نتائج")
        st.markdown("---")
        st.caption("🌍 جلب مجموعة كبيرة من الامراض")
        if st.button("📥 جلب مجموعة واسعة من الامراض", use_container_width=True, type="secondary"):
            if not client_id or not client_secret: st.error("❌ ادخل بيانات الاعتماد اولاً!")
            else:
                with st.spinner("جاري جلب الامراض من ICD-11... قد يستغرق دقيقة"):
                    all_diseases = fetch_all_icd_diseases(language=icd_language)
                    st.session_state['all_icd_diseases'] = all_diseases
                    st.success(f"✅ تم جلب {len(all_diseases)} مرض فريد!")

    st.divider()

    with st.expander("📡 Webhook اشعارات الطوارئ"):
        webhook_url = st.text_input("Webhook URL:", value=st.session_state.get('webhook_url', ''), placeholder="https://hooks.slack.com/...")
        webhook_enabled = st.toggle("تفعيل الاشعارات", value=st.session_state.get('webhook_enabled', False))
        if st.button("💾 حفظ Webhook", use_container_width=True):
            st.session_state['webhook_url'] = webhook_url
            st.session_state['webhook_enabled'] = webhook_enabled
            add_sync_log(f"Webhook {'مفعل' if webhook_enabled else 'معطل'}", "info")
            st.success("✅ تم الحفظ!")

    st.divider()

    with st.expander("🔍 البحث في ارشيف EpiPredict"):
        search_query = st.text_input("ابحث محلياً:", placeholder="مثال: طاعون، سكري، نزيف...", key="local_search_input").strip().lower()

    st.divider()

    with st.expander("🤖 Chatbot طبي", expanded=True):
        st.caption("اسألني عن الامراض والبروتوكولات")
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state['chat_history'][-10:]:
                role_class = "chat-user" if msg['role'] == 'user' else "chat-bot"
                st.markdown(f"""
                <div class="chat-message {role_class}">
                    <b>{'انت' if msg['role'] == 'user' else 'AI طبيب'}:</b> {msg['content']}
                </div>
                """, unsafe_allow_html=True)
        chat_input = st.text_input("رسالتك:", placeholder="اكتب سؤالك هنا...", key="chat_input")
        if st.button("📨 ارسال", use_container_width=True) and chat_input.strip():
            st.session_state['chat_history'].append({'role': 'user', 'content': chat_input})
            response = chatbot_response(chat_input)
            st.session_state['chat_history'].append({'role': 'bot', 'content': response})
            st.rerun()

    st.divider()

    with st.expander("🔄 سجل المزامنة"):
        if st.session_state['sync_log']:
            for log in st.session_state['sync_log'][:15]:
                status_class = log['status']
                st.markdown(f"""
                <div class="sync-log-item {status_class}">
                    <span style="color:#666; font-size:0.7rem;">{log['timestamp']}</span><br>
                    {log['message']}
                </div>
                """, unsafe_allow_html=True)
        else: st.caption("لا توجد سجلات بعد")
        if st.button("🗑️ مسح السجل", use_container_width=True):
            st.session_state['sync_log'] = []
            st.rerun()

st.subheader("📊 لوحة المؤشرات")
total_diseases = len(st.session_state['diseases_db'])
icd_linked = sum(1 for d in st.session_state['diseases_db'].values() if d.get('icd11_code'))
emergency_count = sum(1 for d in st.session_state['diseases_db'].values() if "طوارئ" in d.get('status', '') or "🚨" in d.get('status', ''))
bacterial_count = sum(1 for d in st.session_state['diseases_db'].values() if 'بكتيري' in d.get('category', ''))
viral_count = sum(1 for d in st.session_state['diseases_db'].values() if 'فيروسي' in d.get('category', ''))
cancer_count = sum(1 for d in st.session_state['diseases_db'].values() if 'سرطان' in d.get('category', ''))
icd_fetched = len(st.session_state.get('all_icd_diseases', []))

metrics_cols = st.columns(6)
metrics_data = [("☣️ اجمالي الامراض", total_diseases, "#e94560"), ("🔗 مرتبطة ICD-11", icd_linked, "#00d9ff"), ("🚨 حالات طوارئ", emergency_count, "#ff6b6b"), ("🌍 جلبت من WHO", icd_fetched, "#00ff88"), ("🧬 فيروسية", viral_count, "#ffd700"), ("🎗️ اورام", cancer_count, "#ff69b4")]
for i, (label, value, color) in enumerate(metrics_data):
    with metrics_cols[i]:
        st.markdown(f"""
        <div class="metric-card">
            <div style="font-size:1.8rem; font-weight:900; color:{color};">{value}</div>
            <div style="font-size:0.8rem; color:#a0a0a0;">{label}</div>
        </div>
        """, unsafe_allow_html=True)

has_severe_outbreak = any("طوارئ" in info['status'] or "🚨" in info['status'] for info in st.session_state['diseases_db'].values())
if has_severe_outbreak:
    st.markdown("""
    <div class="emergency-banner">
        🚨 تنبيه وبائي حاد: تم رصد امراض عالية الخطورة! يرجى اتباع البروتوكولات الطبية المشددة.
    </div>
    """, unsafe_allow_html=True)
    for name, info in st.session_state['diseases_db'].items():
        if "طوارئ" in info['status'] or "🚨" in info['status']:
            send_webhook_alert(name, info.get('risk_level', ''), info['status'])

if st.session_state['icd_search_results']:
    st.subheader("🌍 نتائج البحث في ICD-11 (WHO)")
    st.caption(f"تم العثور على {len(st.session_state['icd_search_results'])} مرض من 55,000+ مرض في ICD-11")
    results_container = st.container()
    for i, entity in enumerate(st.session_state['icd_search_results'][:15]):
        title = str(entity.get('title', 'غير معروف')).replace("<em class='found'>", "").replace("</em>", "").replace("<em>", "")
        definition = entity.get('definition', 'لا يوجد تعريف')
        entity_id = entity.get('id', '')
        score = entity.get('score', 0)
        the_code = entity.get('theCode', '---')
        uri = None
        if 'id' in entity: uri = f"http://id.who.int/icd/entity/{entity_id.split('/')[-1]}"
        with results_container:
            col_icd1, col_icd2 = st.columns([3, 1])
            with col_icd1:
                st.markdown(f"### 📋 {title}")
                display_def = definition[:300] + ('...' if len(definition) > 300 else '')
                st.caption(f"**التعريف:** {display_def}")
                if the_code and the_code != '---': st.markdown(f"**🆔 الكود:** `{the_code}`")
                btn_cols = st.columns(4)
                with btn_cols[0]:
                    if st.button(f"📖 التفاصيل", key=f"details_{i}", use_container_width=True):
                        with st.spinner("جاري الجلب..."):
                            details = get_icd_entity(uri, language=icd_language) if uri else None
                            if details: st.json(details)
                            else: st.info("ℹ️ لا توجد تفاصيل اضافية.")
                with btn_cols[1]:
                    if st.button(f"🔗 ربط", key=f"link_{i}", use_container_width=True):
                        disease_name = f"{title} (ICD-11: {the_code})"
                        if disease_name not in st.session_state['diseases_db']:
                            st.session_state['diseases_db'][disease_name] = {"category": "مستورد من ICD-11 🌍", "symptoms": ["غير محدد - يرجى الرجوع للتعريف"], "status": "تحت الدراسة 🟡", "treatment": "يرجى الرجوع للبروتوكولات الطبية المعتمدة.", "risk_level": "غير محدد", "icd11_code": the_code, "icd11_uri": uri, "added_date": datetime.now().strftime("%Y-%m-%d")}
                            add_sync_log(f"تم ربط '{title}' بـ EpiPredict", "success")
                            st.success("✅ تمت الاضافة!")
                            st.rerun()
                        else: st.warning("⚠️ موجود مسبقاً")
                with btn_cols[2]:
                    if st.button(f"👶 فرعية", key=f"children_{i}", use_container_width=True):
                        with st.spinner("جاري البحث..."):
                            children = get_icd_children(uri, language=icd_language) if uri else None
                            if children and 'child' in children:
                                child_list = children['child']
                                st.write(f"**عدد الفرعية:** {len(child_list)}")
                                for child_uri in child_list[:5]:
                                    child_data = get_icd_entity(child_uri.replace("http://", "https://"), icd_language)
                                    if child_data: st.markdown(f"- **{child_data.get('title', 'غير معروف')}**")
                            else: st.info("ℹ️ لا توجد امراض فرعية.")
                with btn_cols[3]:
                    if st.button(f"📋 MMS", key=f"mms_{i}", use_container_width=True):
                        with st.spinner("جاري جلب الكود..."):
                            entity_num = entity_id.split('/')[-1] if entity_id else ''
                            mms_data = get_icd_linearization(entity_num, language=icd_language) if entity_num else None
                            if mms_data: st.json(mms_data)
                            else: st.info("ℹ️ لا يوجد كود MMS.")
            with col_icd2:
                confidence = min(score * 100, 100) if score else 50
                st.progress(max(0.0, min(1.0, float(confidence) / 100.0)), text=f"تطابق: {max(0, int(confidence))}%")
                st.caption(f"🆔 المعرف: `{entity_id.split('/')[-1] if entity_id else 'N/A'}`")
            st.divider()
    if st.button("🗑️ مسح نتائج البحث", use_container_width=True):
        st.session_state['icd_search_results'] = []
        add_sync_log("تم مسح نتائج البحث", "info")
        st.rerun()

if st.session_state.get('all_icd_diseases'):
    st.subheader(f"🌍 جميع الامراض المجلوبة من ICD-11 ({len(st.session_state['all_icd_diseases'])} مرض)")
    filter_text = st.text_input("🔍 تصفية الامراض المجلوبة:", placeholder="اكتب لتصفية...", key="filter_all_icd")
    filtered_icd = st.session_state['all_icd_diseases']
    if filter_text.strip():
        filter_lower = filter_text.lower()
        filtered_icd = [d for d in filtered_icd if filter_lower in d.get('title', '').lower()]
    st.caption(f"عرض {len(filtered_icd)} مرض")
    icd_df_data = []
    for disease in filtered_icd[:100]:
        icd_df_data.append({'الاسم': disease.get('title', ''), 'الكود': disease.get('theCode', '---'), 'التعريف': (disease.get('definition', '')[:100] + '...') if len(disease.get('definition', '')) > 100 else disease.get('definition', ''), 'التطابق': f"{min(disease.get('score', 0) * 100, 100):.0f}%"})
    if icd_df_data: st.dataframe(pd.DataFrame(icd_df_data), use_container_width=True, hide_index=True)
    if st.button("➕ اضافة الكل الى EpiPredict", use_container_width=True):
        added = 0
        for disease in st.session_state['all_icd_diseases'][:50]:
            disease_name = f"{disease.get('title', 'غير معروف')} (ICD-11: {disease.get('theCode', '---')})"
            if disease_name not in st.session_state['diseases_db']:
                st.session_state['diseases_db'][disease_name] = {"category": "مستورد من ICD-11 🌍", "symptoms": ["غير محدد"], "status": "تحت الدراسة 🟡", "treatment": "يرجى الرجوع للبروتوكولات الطبية المعتمدة.", "risk_level": "غير محدد", "icd11_code": disease.get('theCode', ''), "icd11_uri": disease.get('uri', ''), "added_date": datetime.now().strftime("%Y-%m-%d")}
                added += 1
        add_sync_log(f"تم اضافة {added} مرض من ICD-11", "success")
        st.success(f"✅ تمت اضافة {added} مرض!")
        st.rerun()

st.divider()

st.subheader("📚 السجل الطبي الذكي")
tab1, tab2, tab3 = st.tabs(["📋 قائمة الامراض + تصنيف AI", "🗺️ الخريطة الجغرافية", "📈 التحليلات المتقدمة"])

with tab1:
    st.markdown("##### ⚡ لوحة التحكم السريعة")
    quick_cols = st.columns(4)
    with quick_cols[0]:
        if st.button("🔄 مزامنة ICD-11", use_container_width=True, type="primary"):
            add_sync_log("بدء مزامنة ذكية مع ICD-11", "info")
            synced = 0
            for name, info in list(st.session_state['diseases_db'].items()):
                if not info.get('icd11_code'):
                    search_term = name.split('(')[0].strip()
                    results = search_icd11(search_term, language="ar")
                    if results and results.get('destinationEntities'):
                        first = results['destinationEntities'][0]
                        info['icd11_code'] = first.get('theCode', '')
                        info['icd11_uri'] = f"http://id.who.int/icd/entity/{first.get('id', '').split('/')[-1]}"
                        synced += 1
            add_sync_log(f"تم مزامنة {synced} مرض تلقائياً", "success")
            st.success(f"✅ تمت مزامنة {synced} مرض!")
            st.rerun()
    with quick_cols[1]:
        if st.button("🧠 تحديث AI", use_container_width=True):
            add_sync_log("تم تحديث التصنيف الذكي", "success")
            st.success("✅ تم تحديث AI!")
            st.rerun()
    with quick_cols[2]:
        if st.button("🗑️ مسح المستورد", use_container_width=True):
            imported = [k for k, v in st.session_state['diseases_db'].items() if "ICD-11" in v.get('category', '')]
            for k in imported: del st.session_state['diseases_db'][k]
            add_sync_log(f"تم مسح {len(imported)} مرض مستورد", "warning")
            st.success(f"✅ تم مسح {len(imported)} مرض!")
            st.rerun()
    with quick_cols[3]:
        if st.button("🔄 اعادة تعيين", use_container_width=True):
            st.session_state['diseases_db'] = {}
            st.session_state['all_icd_diseases'] = []
            st.session_state['map_data'] = pd.DataFrame({'lat': [], 'lon': [], 'risk_score': [], 'disease_name': []})
            st.session_state['sync_log'] = []
            st.session_state['chat_history'] = []
            st.session_state['export_history'] = []
            add_sync_log("تم اعادة تعيين النظام", "warning")
            st.success("✅ تم اعادة التعيين!")
            st.rerun()

    st.divider()
    st.markdown("##### 📥 تصدير البيانات")
    export_cols = st.columns(3)
    with export_cols[0]:
        if st.button("📄 تصدير CSV", use_container_width=True):
            csv_data, filename = export_to_csv()
            st.download_button(label="⬇️ تحميل CSV", data=csv_data, file_name=filename, mime="text/csv", use_container_width=True)
    with export_cols[1]:
        if st.button("📊 تصدير Excel", use_container_width=True):
            excel_data, filename = export_to_excel()
            st.download_button(label="⬇️ تحميل Excel", data=excel_data, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with export_cols[2]:
        if st.session_state['export_history']:
            with st.expander("📜 تاريخ التصدير"):
                for exp in st.session_state['export_history'][-5:]:
                    st.caption(f"{exp['timestamp']} - {exp['filename']} ({exp['records']} سجل)")

    st.divider()
    filtered_db = {}
    for d_name, d_info in st.session_state['diseases_db'].items():
        symptoms_str = " ".join(d_info.get('symptoms', [])).lower()
        if (not search_query or search_query in d_name.lower() or search_query in d_info.get('category', '').lower() or search_query in symptoms_str):
            filtered_db[d_name] = d_info
    if filtered_db:
        st.caption(f"عدد النتائج: {len(filtered_db)}")
        for d_name, d_info in filtered_db.items():
            classification = ai_classify_disease(d_info)
            if "طوارئ" in d_info.get('category', '') or "نزفي" in d_info.get('category', ''): icon = "☣️"
            elif "سرطان" in d_info.get('category', '') or "اورام" in d_info.get('category', ''): icon = "🎗️"
            elif "ICD-11" in d_info.get('category', ''): icon = "🌍"
            elif "فيروسي" in d_info.get('category', ''): icon = "🧬"
            elif "بكتيري" in d_info.get('category', ''): icon = "🦠"
            elif "قلب" in d_info.get('category', ''): icon = "❤️"
            elif "سكري" in d_info.get('category', ''): icon = "💉"
            else: icon = "📌"
            with st.expander(f"{icon} {d_name} — [{d_info.get('category', 'غير مصنف')}]"):
                col_info, col_ai = st.columns([2, 1])
                with col_info:
                    if 'icd11_code' in d_info and d_info['icd11_code']: st.markdown(f"🏷️ **كود ICD-11:** `{d_info['icd11_code']}`")
                    st.write(f"**حالة المراقبة:** {d_info.get('status', 'غير محدد')}")
                    st.write(f"**الاعراض:** {', '.join(d_info.get('symptoms', ['غير محدد']))}")
                    st.write(f"**درجة الخطر:** {d_info.get('risk_level', 'غير محدد')}")
                    if "مرتفع جداً" in d_info.get('risk_level', ''): st.error(f"**البروتوكول:** {d_info.get('treatment', 'غير متوفر')}")
                    else: st.success(f"**العلاج:** {d_info.get('treatment', 'غير متوفر')}")
                    if 'icd11_uri' in d_info and d_info['icd11_uri']:
                        who_url = d_info['icd11_uri'].replace("http://", "https://")
                        st.markdown(f"[🔗 عرض في WHO]({who_url})")
                with col_ai:
                    st.markdown(f"""
                    <div style="background:#0a0a0a; border-radius:10px; padding:1rem; border:1px solid {classification['severity_color']};">
                        <h4 style="color:{classification['severity_color']}; margin:0 0 0.5rem 0;">🧠 تصنيف AI</h4>
                        <p style="margin:0.3rem 0;"><b>الشدة:</b> <span style="color:{classification['severity_color']}">{classification['severity']}</span></p>
                        <p style="margin:0.3rem 0;"><b>النوع:</b> {classification['type']}</p>
                        <p style="margin:0.3rem 0;"><b>الفصل:</b> {classification['icd_chapter']}</p>
                        <p style="margin:0.3rem 0;"><b>الاولوية:</b> {'⭐' * classification['priority']}</p>
                    </div>
                    """, unsafe_allow_html=True)
    else: st.warning("⚠️ لا توجد نتائج تطابق بحثك.")

with tab2:
    st.subheader("🗺️ خريطة التوزيع الجغرافي للعدوى")
    if not st.session_state['map_data'].empty:
        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/dark-v10',
            initial_view_state=pdk.ViewState(latitude=st.session_state['map_data']['lat'].mean(), longitude=st.session_state['map_data']['lon'].mean(), zoom=5, pitch=60, bearing=30),
            layers=[pdk.Layer('ColumnLayer', data=st.session_state['map_data'], get_position='[lon, lat]', get_elevation='risk_score', elevation_scale=500, radius=15000, get_fill_color='[risk_score * 2.5, 50, 255 - risk_score * 2.5, 200]', pickable=True, auto_highlight=True, extruded=True)],
            tooltip={'html': '<b>{disease_name}</b><br>مستوى الخطر: {risk_score}/100', 'style': {'backgroundColor': '#16213e', 'color': 'white'}}
        ))
        st.markdown("##### ➕ اضافة موقع جديد")
        new_cols = st.columns(4)
        with new_cols[0]: new_lat = st.number_input("خط العرض:", value=30.0, format="%.4f")
        with new_cols[1]: new_lon = st.number_input("خط الطول:", value=31.0, format="%.4f")
        with new_cols[2]: new_risk = st.slider("الخطر:", 0, 100, 50)
        with new_cols[3]: new_disease = st.text_input("المرض:", value="جديد")
        if st.button("➕ اضافة للخريطة", use_container_width=True):
            new_row = pd.DataFrame({'lat': [new_lat], 'lon': [new_lon], 'risk_score': [new_risk], 'disease_name': [new_disease]})
            st.session_state['map_data'] = pd.concat([st.session_state['map_data'], new_row], ignore_index=True)
            add_sync_log(f"اضافة موقع: {new_disease} ({new_lat}, {new_lon})", "success")
            st.success("✅ تمت الاضافة!")
            st.rerun()
    else: st.info("ℹ️ لا توجد بيانات خريطة بعد.")

with tab3:
    st.subheader("📈 التحليلات المتقدمة")
    if st.session_state['diseases_db']:
        analysis_data = []
        for name, info in st.session_state['diseases_db'].items():
            classification = ai_classify_disease(info)
            analysis_data.append({'name': name, 'category': info.get('category', ''), 'risk_level': info.get('risk_level', ''), 'status': info.get('status', ''), 'severity': classification['severity'], 'type': classification['type'], 'icd_linked': 'نعم' if info.get('icd11_code') else 'لا', 'has_icd': bool(info.get('icd11_code'))})
        df_analysis = pd.DataFrame(analysis_data)
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            fig_type = px.pie(df_analysis, names='type', title='توزيع الامراض حسب النوع', color_discrete_sequence=px.colors.sequential.Reds, template='plotly_dark')
            fig_type.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_type, use_container_width=True)
        with col_chart2:
            severity_counts = df_analysis['severity'].value_counts().reset_index()
            severity_counts.columns = ['severity', 'count']
            fig_severity = px.bar(severity_counts, x='severity', y='count', title='توزيع الامراض حسب مستوى الشدة (AI)', color='severity', color_discrete_map={'حرج': '#e94560', 'عالي': '#ff6b6b', 'متوسط': '#ffd700', 'منخفض': '#00d9ff'}, template='plotly_dark')
            st.plotly_chart(fig_severity, use_container_width=True)
        col_chart3, col_chart4 = st.columns(2)
        with col_chart3:
            icd_counts = df_analysis['icd_linked'].value_counts().reset_index()
            icd_counts.columns = ['linked', 'count']
            fig_icd = px.pie(icd_counts, names='linked', values='count', title='نسبة ربط ICD-11', color='linked', color_discrete_map={'نعم': '#00d9ff', 'لا': '#e94560'}, template='plotly_dark', hole=0.4)
            st.plotly_chart(fig_icd, use_container_width=True)
        with col_chart4:
            risk_mapping = {'مرتفع جداً (حالة طوارئ)': 5, 'مرتفع جداً': 4, 'مرتفع': 3, 'متوسط': 2, 'منخفض': 1, 'غير محدد': 0}
            df_analysis['risk_num'] = df_analysis['risk_level'].map(lambda x: risk_mapping.get(x, 0))
            fig_risk = px.bar(df_analysis.sort_values('risk_num', ascending=False), x='name', y='risk_num', title='مستوى الخطر لكل مرض', color='risk_num', color_continuous_scale='Reds', template='plotly_dark')
            fig_risk.update_xaxes(tickangle=45)
            st.plotly_chart(fig_risk, use_container_width=True)
        st.markdown("##### 📋 ملخص البيانات التحليلي")
        summary_df = df_analysis[['name', 'type', 'severity', 'icd_linked']].copy()
        summary_df.columns = ['المرض', 'النوع (AI)', 'الشدة (AI)', 'ICD-11']
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    else: st.info("ℹ️ لا توجد بيانات كافية للتحليل.")

st.divider()
footer_cols = st.columns(3)
with footer_cols[0]:
    st.caption("☣️ EpiPredict + ICD-11 Pro v8.0")
    st.caption("Powered by WHO ICD-11 API")
with footer_cols[1]:
    st.caption("🤖 AI Classification Engine")
    st.caption("📡 Webhook Notifications")
with footer_cols[2]:
    st.caption("🌐 Multi-Language Support")
    st.caption("📱 Responsive Design")
    if st.session_state.get('last_sync'): st.caption(f"🔄 اخر مزامنة: {st.session_state['last_sync']}")