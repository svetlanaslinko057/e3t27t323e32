/**
 * ContactModalContext — site-wide provider so any CTA can open the
 * lead-capture modal: `const { openContact } = useContactModal();`
 * openContact({ source, bannerId, title, subtitle, prefillMessage }).
 */
import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import ContactModal from '@/components/ContactModal';

const ContactModalContext = createContext({ openContact: () => {}, closeContact: () => {} });

export const useContactModal = () => useContext(ContactModalContext);

export const ContactModalProvider = ({ children }) => {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState({});

  const openContact = useCallback((opts = {}) => {
    setOptions(opts || {});
    setOpen(true);
  }, []);
  const closeContact = useCallback(() => setOpen(false), []);

  const value = useMemo(() => ({ openContact, closeContact }), [openContact, closeContact]);

  return (
    <ContactModalContext.Provider value={value}>
      {children}
      <ContactModal open={open} onClose={closeContact} options={options} />
    </ContactModalContext.Provider>
  );
};

export default ContactModalProvider;
