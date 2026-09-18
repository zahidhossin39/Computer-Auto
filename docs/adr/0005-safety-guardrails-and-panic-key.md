# Safety Guardrail Verification and Emergency Panic Key

To prevent irreversible accidents during autonomous GUI execution, any action classified as destructive (file deletion, closing unsaved files, financial transactions, sending external messages) requires explicit verbal confirmation before execution. Additionally, a global physical panic key (Escape) immediately terminates all active input threads and returns system control to the user.
