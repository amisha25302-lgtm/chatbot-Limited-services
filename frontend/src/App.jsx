import { useState, useEffect, useRef } from 'react';
import './App.css';

// Translation dictionary for English and Hindi support
const translations = {
  en: {
    brand_title: "SewaSetu RAG",
    brand_sub: "AI Sahayak",
    search_placeholder: "Search services or ID...",
    directory_title: "Services Directory",
    online_agent: "Online RAG Agent",
    welcome_title: "Welcome to SewaSetu RAG Assistant",
    welcome_desc: "Ask me anything about CG citizen services, document list, kiosk fees, or timelines. Click any service on the left to view its details instantly.",
    input_placeholder: "Ask about documents, fees, rules...",
    send: "Send",
    service_details: "Service Details",
    service_name: "Service Name",
    department: "Department",
    time_limit: "Time Limit (SLA)",
    contact_authority: "Contact Authority",
    fee_info: "Fee Information",
    online_fee: "Online Portal Fee",
    kiosk_fee: "Kiosk Center Fee",
    apply_link: "Apply Link",
    apply_desc: "This is an internal service. You can login and apply on the Sewa Setu portal.",
    apply_btn: "Go to Sewa Setu Portal",
    required_docs: "Required Documents",
    form_fields: "Application Form Fields",
    mandatory: "Mandatory",
    optional: "Optional",
    internal: "Internal",
    external: "External",
    error_fetch: "Error loading service catalog.",
    error_chat: "Error getting response from local LLM. Please make sure Ollama is running.",
    error_details: "Error loading service details."
  },
  hi: {
    brand_title: "सेवासेतु RAG",
    brand_sub: "एआई सहायक",
    search_placeholder: "सेवाएं या आईडी खोजें...",
    directory_title: "सेवाएं निर्देशिका",
    online_agent: "ऑनलाइन आरएजी एजेंट",
    welcome_title: "सेवासेतु आरएजी सहायक में आपका स्वागत है",
    welcome_desc: "छत्तीसगढ़ नागरिक सेवाओं, आवश्यक दस्तावेजों की सूची, कियोस्क शुल्क या समय सीमा के बारे में कुछ भी पूछें। विवरण देखने के लिए बाईं ओर किसी भी सेवा पर क्लिक करें।",
    input_placeholder: "दस्तावेजों, शुल्कों, नियमों के बारे में पूछें...",
    send: "भेजें",
    service_details: "सेवा का विवरण",
    service_name: "सेवा का नाम",
    department: "विभाग",
    time_limit: "समय सीमा (SLA)",
    contact_authority: "संपर्क प्राधिकारी",
    fee_info: "शुल्क की जानकारी",
    online_fee: "ऑनलाइन पोर्टल शुल्क",
    kiosk_fee: "कियोस्क केंद्र शुल्क",
    apply_link: "आवेदन लिंक",
    apply_desc: "यह एक आंतरिक सेवा है। आप लॉग इन करके सेवा सेतु पोर्टल पर आवेदन कर सकते हैं।",
    apply_btn: "सेवा सेतु पोर्टल पर जाएं",
    required_docs: "आवश्यक दस्तावेज़",
    form_fields: "आवेदन पत्र के फ़ील्ड",
    mandatory: "अनिवार्य",
    optional: "वैकल्पिक",
    internal: "आंतरिक",
    external: "बाहरी",
    error_fetch: "सेवा सूची लोड करने में त्रुटि।",
    error_chat: "स्थानीय एलएलएम से उत्तर प्राप्त करने में त्रुटि। कृपया सुनिश्चित करें कि ओलामा चल रहा है।",
    error_details: "सेवा विवरण लोड करने में त्रुटि।"
  }
};

// Pure React Markdown parser utility to safely format chatbot responses
function parseMarkdown(text) {
  if (!text) return null;
  const lines = text.split('\n');
  let inList = false;
  let listItems = [];
  const elements = [];

  const parseInline = (str) => {
    // Matches **bold text**
    const parts = str.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, index) => {
      if (index % 2 === 1) {
        return <strong key={index}>{part}</strong>;
      }
      return part;
    });
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (!inList) {
        inList = true;
        listItems = [];
      }
      listItems.push(<li key={`li-${index}`} style={{ marginLeft: '12px' }}>{parseInline(trimmed.substring(2))}</li>);
    } else if (trimmed.match(/^\d+\.\s/)) {
      if (!inList) {
        inList = true;
        listItems = [];
      }
      const itemText = trimmed.replace(/^\d+\.\s/, '');
      listItems.push(<li key={`li-${index}`} style={{ marginLeft: '12px' }}>{parseInline(itemText)}</li>);
    } else {
      if (inList) {
        elements.push(
          <ul key={`ul-${index}`} style={{ margin: '8px 0 12px 16px', paddingLeft: '12px', listStyleType: 'disc' }}>
            {listItems}
          </ul>
        );
        inList = false;
        listItems = [];
      }

      if (trimmed.startsWith('### ')) {
        elements.push(<h4 key={index} style={{ margin: '14px 0 6px', fontSize: '15px', fontWeight: 700 }}>{parseInline(trimmed.substring(4))}</h4>);
      } else if (trimmed.startsWith('## ')) {
        elements.push(<h3 key={index} style={{ margin: '16px 0 8px', fontSize: '16px', fontWeight: 700 }}>{parseInline(trimmed.substring(3))}</h3>);
      } else if (trimmed.startsWith('# ')) {
        elements.push(<h2 key={index} style={{ margin: '18px 0 10px', fontSize: '18px', fontWeight: 700 }}>{parseInline(trimmed.substring(2))}</h2>);
      } else if (trimmed) {
        elements.push(<p key={index} style={{ marginBottom: '8px' }}>{parseInline(line)}</p>);
      } else {
        elements.push(<div key={index} style={{ height: '8px' }}></div>);
      }
    }
  });

  if (inList) {
    elements.push(
      <ul key="ul-end" style={{ margin: '8px 0 12px 16px', paddingLeft: '12px', listStyleType: 'disc' }}>
        {listItems}
      </ul>
    );
  }

  return elements;
}

function App() {
  const [lang, setLang] = useState('en');
  const [services, setServices] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSno, setSelectedSno] = useState(null);
  
  // Service Details States
  const [details, setDetails] = useState(null);
  const [isDetailsLoading, setIsDetailsLoading] = useState(false);
  const [detailsPanelOpen, setDetailsPanelOpen] = useState(false);
  
  // Chat States
  const [chatMessages, setChatMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);

  // References
  const messagesEndRef = useRef(null);
  const t = translations[lang];

  // Fetch Services list on startup
  useEffect(() => {
    const fetchServices = async () => {
      try {
        const response = await fetch('/api/services');
        if (response.ok) {
          const data = await response.json();
          setServices(data);
        } else {
          console.error('Failed to fetch services:', response.status);
        }
      } catch (err) {
        console.error('Error fetching services:', err);
      }
    };
    fetchServices();
  }, []);

  // Fetch selected service details when selectedSno or language changes
  useEffect(() => {
    if (!selectedSno) {
      setDetails(null);
      return;
    }

    const fetchDetails = async () => {
      setIsDetailsLoading(true);
      try {
        const response = await fetch(`/api/services/${selectedSno}?lang=${lang}`);
        if (response.ok) {
          const data = await response.json();
          setDetails(data);
          setDetailsPanelOpen(true);
        } else {
          console.error('Failed to fetch service details');
        }
      } catch (err) {
        console.error('Error fetching details:', err);
      } finally {
        setIsDetailsLoading(false);
      }
    };

    fetchDetails();
  }, [selectedSno, lang]);

  // Scroll to bottom of chat when new message arrives or loading changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isChatLoading]);

  // Handle Search Input in left panel
  const filteredServices = services.filter((srv) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;

    const nameEn = (srv.name_en || '').toLowerCase();
    const nameHi = (srv.name_hi || '').toLowerCase();
    const deptEn = (srv.dept_en || '').toLowerCase();
    const deptHi = (srv.dept_hi || '').toLowerCase();
    const sId = (srv.service_id || '').toLowerCase();
    const sNo = (srv.sno || '').toLowerCase();

    return (
      nameEn.includes(query) ||
      nameHi.includes(query) ||
      deptEn.includes(query) ||
      deptHi.includes(query) ||
      sId.includes(query) ||
      sNo.includes(query)
    );
  });

  // Handle RAG Chat submit
  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || isChatLoading) return;

    const userQuery = inputText.trim();
    setInputText('');

    // Append user message to state
    const newMessages = [...chatMessages, { role: 'user', content: userQuery }];
    setChatMessages(newMessages);
    setIsChatLoading(true);

    let activeSno = selectedSno;

    // Smart Catalog Mapping: Call search endpoint to see if query maps to a specific catalog item
    try {
      const searchRes = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userQuery, language: lang })
      });
      if (searchRes.ok) {
        const mapData = await searchRes.json();
        if (mapData.sno) {
          setSelectedSno(mapData.sno);
          activeSno = mapData.sno;
        }
      }
    } catch (searchErr) {
      console.warn('Mapping search failed, falling back to chat only:', searchErr);
    }

    // Call chat endpoint
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: newMessages,
          selected_sno: activeSno,
          language: lang
        })
      });

      if (response.ok) {
        const data = await response.json();
        setChatMessages((prev) => [
          ...prev,
          { role: 'assistant', content: data.response }
        ]);
      } else {
        setChatMessages((prev) => [
          ...prev,
          { role: 'assistant', content: t.error_chat }
        ]);
      }
    } catch (err) {
      console.error('Chat API Error:', err);
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: t.error_chat }
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="app-container">
      {/* 1. LEFT SIDEBAR: SERVICES DIRECTORY */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <h1>{t.brand_title}</h1>
            <div className="brand-subtitle">{t.brand_sub}</div>
          </div>
          
          <div className="lang-selector">
            <button 
              className={`lang-btn ${lang === 'en' ? 'active' : ''}`}
              onClick={() => setLang('en')}
            >
              English
            </button>
            <button 
              className={`lang-btn ${lang === 'hi' ? 'active' : ''}`}
              onClick={() => setLang('hi')}
            >
              हिंदी
            </button>
          </div>

          <div className="search-container">
            <input 
              type="text" 
              className="search-input"
              placeholder={t.search_placeholder}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <svg 
              className="search-icon" 
              width="16" 
              height="16" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2" 
              viewBox="0 0 24 24"
            >
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </div>
        </div>

        <div className="services-list-container">
          <h2 className="directory-title">
            {t.directory_title} ({filteredServices.length})
          </h2>
          {filteredServices.map((srv) => (
            <div 
              key={srv.sno}
              className={`service-item ${selectedSno === srv.sno ? 'active' : ''}`}
              onClick={() => setSelectedSno(srv.sno)}
            >
              <div className="service-dept">
                {lang === 'hi' ? srv.dept_hi : srv.dept_en}
              </div>
              <div className="service-name">
                {lang === 'hi' ? srv.name_hi : srv.name_en}
              </div>
              <div className="service-footer">
                <span className="service-id">ID: {srv.service_id}</span>
                <span className="badge internal">{t.internal}</span>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* 2. CENTER PANEL: CHAT INTERFACE */}
      <main className="chat-panel">
        <header className="chat-header">
          <div className="chat-header-info">
            <h2>{t.brand_title} {lang === 'hi' ? 'चैट सहायक' : 'Chat Assistant'}</h2>
            <div className="chat-status">
              <span className="status-dot"></span>
              {t.online_agent}
            </div>
          </div>
          {selectedSno && !detailsPanelOpen && (
            <button 
              className="lang-btn" 
              onClick={() => setDetailsPanelOpen(true)}
              style={{ width: 'auto', padding: '6px 12px' }}
            >
              {lang === 'hi' ? 'विवरण देखें' : 'View Details'}
            </button>
          )}
        </header>

        <div className="chat-messages">
          {chatMessages.length === 0 ? (
            <div className="welcome-container">
              <div className="welcome-icon-box">⚡</div>
              <h2>{t.welcome_title}</h2>
              <p>{t.welcome_desc}</p>
            </div>
          ) : (
            chatMessages.map((msg, index) => (
              <div key={index} className={`message-row ${msg.role}`}>
                <div className="message-bubble">
                  {msg.role === 'user' ? msg.content : parseMarkdown(msg.content)}
                </div>
              </div>
            ))
          )}

          {isChatLoading && (
            <div className="message-row assistant">
              <div className="message-bubble" style={{ padding: '12px 20px' }}>
                <div className="typing-indicator">
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-container">
          <form className="chat-input-form" onSubmit={handleSendMessage}>
            <textarea 
              className="chat-textarea"
              placeholder={t.input_placeholder}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button 
              type="submit" 
              className="chat-send-btn"
              disabled={!inputText.trim() || isChatLoading}
            >
              <svg 
                width="18" 
                height="18" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="currentColor" 
                strokeWidth="2"
              >
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </form>
        </div>
      </main>

      {/* 3. RIGHT PANEL: SERVICE DETAILS */}
      {detailsPanelOpen && (
        <aside className="details-panel">
          <div className="details-header">
            <h2>{t.service_details}</h2>
            <button 
              className="close-btn"
              onClick={() => setDetailsPanelOpen(false)}
            >
              ✕
            </button>
          </div>

          <div className="details-content">
            {isDetailsLoading ? (
              <div className="spinner-container">
                <div className="spinner"></div>
              </div>
            ) : details ? (
              <>
                <div className="detail-section">
                  <div className="detail-section-title">{t.service_name}</div>
                  <div className="detail-text-bold">{details.name}</div>
                </div>

                <div className="detail-section">
                  <div className="detail-section-title">{t.department}</div>
                  <div className="detail-text-secondary">{details.department}</div>
                </div>

                <div className="detail-section meta-grid">
                  <div className="meta-box">
                    <div className="meta-label">{t.time_limit}</div>
                    <div className="meta-value">{details.time_limit || details.sla || 'N/A'}</div>
                  </div>
                  <div className="meta-box">
                    <div className="meta-label">{t.contact_authority}</div>
                    <div className="meta-value">{details.contact_details || 'N/A'}</div>
                  </div>
                </div>

                <div className="detail-section">
                  <div className="detail-section-title">{t.fee_info}</div>
                  <div className="fee-cards">
                    <div className="fee-card">
                      <div className="fee-card-label">{t.online_fee}</div>
                      <div className="fee-card-value">
                        {details.fees?.online_fee ? `₹${details.fees.online_fee}` : 'N/A'}
                      </div>
                    </div>
                    <div className="fee-card">
                      <div className="fee-card-label">{t.kiosk_fee}</div>
                      <div className="fee-card-value">
                        {details.fees?.kiosk_fee ? `₹${details.fees.kiosk_fee}` : 'N/A'}
                      </div>
                    </div>
                  </div>
                  {details.fees?.raw_text && (
                    <div className="fee-note">
                      <strong>Note:</strong> {details.fees.raw_text}
                    </div>
                  )}
                </div>

                {details.details_link && (
                  <div className="detail-section">
                    <div className="detail-section-title">{t.apply_link}</div>
                    <div className="apply-box">
                      <p className="apply-text">{t.apply_desc}</p>
                      <a 
                        href={details.details_link} 
                        target="_blank" 
                        rel="noreferrer"
                        className="apply-btn"
                      >
                        {t.apply_btn}
                      </a>
                    </div>
                  </div>
                )}

                {details.required_documents && details.required_documents.length > 0 && (
                  <div className="detail-section">
                    <div className="detail-section-title">{t.required_docs}</div>
                    <div className="documents-list">
                      {details.required_documents.map((doc, idx) => {
                        const isMandatory = (doc.mandatory || '').toLowerCase() === 'yes' || (doc.mandatory || '').trim() === 'हाँ';
                        const hasMultipleOptions = doc.supporting_documents && doc.supporting_documents.length > 1;
                        const hasSingleDiffOption = doc.supporting_documents && doc.supporting_documents.length === 1 && doc.supporting_documents[0].name !== doc.document_type;
                        const showOptions = hasMultipleOptions || hasSingleDiffOption;

                        return (
                          <div key={idx} className="document-card-wrapper" style={{ marginBottom: '12px', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-app)', padding: '10px 14px' }}>
                            <div className="document-card" style={{ border: 'none', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                              <div className="document-info" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                <span className="document-bullet" style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--primary-blue)', flexShrink: 0 }}></span>
                                <span className="document-name" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.4 }}>{doc.document_type}</span>
                              </div>
                              <span className={`document-badge ${isMandatory ? 'mandatory' : 'optional'}`}>
                                {isMandatory ? t.mandatory : t.optional}
                              </span>
                            </div>
                            {showOptions && (
                              <div className="document-options" style={{ paddingLeft: '18px', marginTop: '8px', borderTop: '1px dashed var(--border-color)', paddingTop: '8px' }}>
                                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px', color: 'var(--primary-blue)' }}>
                                  {lang === 'hi' ? 'वैकल्पिक दस्तावेज़ (कोई एक):' : 'Options (choose one):'}
                                </div>
                                <ul style={{ listStyleType: 'disc', paddingLeft: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                                  {doc.supporting_documents.map((subDoc, subIdx) => (
                                    <li key={subIdx} style={{ marginBottom: '4px', lineHeight: 1.4 }}>
                                      {subDoc.name}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {details.form_fields && details.form_fields.length > 0 && (
                  <div className="detail-section">
                    <div className="detail-section-title">{t.form_fields}</div>
                    <div className="fields-grid">
                      {details.form_fields.map((field, idx) => {
                        const isSection = (field.input_type || '').toLowerCase() === 'section lebel';
                        if (isSection) {
                          return (
                            <div 
                              key={idx} 
                              style={{ 
                                fontWeight: 700, 
                                fontSize: '11px', 
                                color: 'var(--primary-blue)', 
                                borderBottom: '1px solid var(--border-color)',
                                padding: '12px 0 4px 0',
                                textTransform: 'uppercase',
                                letterSpacing: '0.5px'
                              }}
                            >
                              {field.label}
                            </div>
                          );
                        }
                        return (
                          <div key={idx} className="field-row">
                            <span className="field-label">{field.label}</span>
                            <span className="field-type">
                              {field.input_type || 'text'} ({field.data_type || 'char'})
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="detail-text-secondary" style={{ textAlign: 'center', marginTop: '40px' }}>
                Select a service to view details.
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}

export default App;
