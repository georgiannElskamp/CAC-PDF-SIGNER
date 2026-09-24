# Release 0.9.0

Changes through research commit `9c18593ae6953a3b06412534da54557bd4eb58c9`.

- Sign ONLYOFFICE PDF form signature boxes with CAC (#19)
- Sync accepted release into research (#21)
- Bind ONLYOFFICE form signatures to loaded PDF (#24)

Coverage includes Windows/Linux hosted installation and form review handoff, Windows CNG, Linux restart and simulated CAC signing, PDF integrity/layout and recovery failures. Windows standard-user profile initialization remains a diagnostic limit; physical reader/CAC coverage is not established by simulation. See docs/TESTING.md.
