"""Built-in translation catalog so language selection works offline.

Each entry is (English, Portuguese (Portugal), Indonesian, Tetum). Brazilian
Portuguese uses the Portuguese text with the overrides in ``PT_BR``.
"""

LANGUAGES = {
    "id": "Bahasa Indonesia",
    "tet": "Tetun",
    "pt_PT": "Português (Portugal)",
    "pt_BR": "Português (Brasil)",
    "en": "English (International)",
}

_T = {
    # Login and profile -----------------------------------------------------
    "sign_in": ("Sign in to Eduka-Konekta", "Entrar no Eduka-Konekta", "Masuk ke Eduka-Konekta", "Tama ba Eduka-Konekta"),
    "welcome": (
        "School communication, exams and attendance directly over your school network — no internet or server needed.",
        "Comunicação escolar, exames e presenças diretamente pela rede da escola — sem internet nem servidor.",
        "Komunikasi sekolah, ujian, dan absensi langsung melalui jaringan sekolah — tanpa internet dan tanpa server.",
        "Komunikasaun eskola, ezame no prezensa diretamente liuhusi rede eskola — la presiza internet ka servidór.",
    ),
    "login_hint": (
        "Fill in your real details. Everyone at the same school with the same school name will see you.",
        "Preencha os seus dados reais. Todos na mesma escola, com o mesmo nome de escola, poderão vê-lo.",
        "Isi data asli Anda. Semua pengguna dengan nama sekolah yang sama akan melihat Anda.",
        "Prense ita-nia dadus loloos. Ema hotu ho naran eskola hanesan sei haree ita.",
    ),
    "hero_chat": (
        "Class, school, teacher and private chats with photos, voice and documents",
        "Conversas da turma, da escola, dos professores e privadas com fotos, voz e documentos",
        "Chat kelas, sekolah, guru, dan pribadi dengan foto, suara, dan dokumen",
        "Chat klase, eskola, profesór no privadu ho foto, lian no dokumentu",
    ),
    "hero_exams": (
        "Exams and assignments: teachers send questions, students answer and send back",
        "Exames e trabalhos: o professor envia as perguntas, o aluno responde e devolve",
        "Ujian dan tugas: guru mengirim soal, siswa mengerjakan lalu mengirim kembali",
        "Ezame no tarefa: profesór haruka pergunta, estudante hatán no haruka fali",
    ),
    "hero_attendance": (
        "One-click attendance with CSV export for the class register",
        "Presenças num clique com exportação CSV para o livro de ponto",
        "Absensi satu klik dengan ekspor CSV untuk buku kehadiran",
        "Prezensa ho klik ida no esporta CSV ba livru prezensa",
    ),
    "hero_network": (
        "Works on Wi-Fi and LAN cable, even mixed, with automatic relay",
        "Funciona em Wi-Fi e cabo LAN, mesmo misturados, com retransmissão automática",
        "Bekerja di Wi-Fi dan kabel LAN, bahkan campuran, dengan relay otomatis",
        "Funsiona iha Wi-Fi no kabu LAN, maski kahur, ho relay automátiku",
    ),
    "no_password": (
        "No password • No central server • Same-school network only",
        "Sem palavra-passe • Sem servidor central • Apenas na rede da escola",
        "Tanpa kata sandi • Tanpa server pusat • Hanya jaringan sekolah yang sama",
        "Laiha senha • Laiha servidór sentrál • Rede eskola hanesan de'it",
    ),
    "language": ("Language", "Idioma", "Bahasa", "Lian"),
    "full_name": ("Full name", "Nome completo", "Nama lengkap", "Naran kompletu"),
    "full_name_hint": ("First name and family name, e.g. Maria da Silva", "Nome e apelido, ex.: Maria da Silva", "Nama depan dan nama keluarga, mis. Maria da Silva", "Naran no apelidu, ez.: Maria da Silva"),
    "school": ("School name", "Nome da escola", "Nama sekolah", "Naran eskola"),
    "school_hint": ("Must be written the same on every computer", "Deve ser escrito igual em todos os computadores", "Harus ditulis sama di semua komputer", "Tenke hakerek hanesan iha komputadór hotu"),
    "role": ("I am a", "Sou", "Saya adalah", "Ha'u mak"),
    "student": ("Student", "Aluno(a)", "Siswa", "Estudante"),
    "teacher": ("Teacher", "Professor(a)", "Guru", "Profesór(a)"),
    "age": ("Age", "Idade", "Umur", "Tinan"),
    "class": ("Class", "Turma", "Kelas", "Klase"),
    "class_hint": ("e.g. 10A", "ex.: 10A", "mis. 10A", "ez.: 10A"),
    "room": ("Classroom", "Sala", "Ruang kelas", "Sala"),
    "room_hint": ("e.g. Room 2", "ex.: Sala 2", "mis. Ruang 2", "ez.: Sala 2"),
    "subject": ("Subject taught", "Disciplina que leciona", "Mata pelajaran yang diajar", "Matéria ne'ebé hanorin"),
    "subject_hint": ("e.g. Mathematics", "ex.: Matemática", "mis. Matematika", "ez.: Matemátika"),
    "continue": ("Connect to the school network", "Ligar à rede da escola", "Masuk ke jaringan sekolah", "Konekta ba rede eskola"),
    "profile_error": ("Please correct the following", "Corrija o seguinte", "Mohon perbaiki hal berikut", "Favór hadi'a buat hirak-ne'e"),
    "name_error": ("Enter a first name and family name using letters only.", "Introduza nome e apelido apenas com letras.", "Masukkan nama depan dan nama keluarga hanya dengan huruf.", "Hakerek naran no apelidu ho letra de'it."),
    "school_error": ("Enter the full school name.", "Introduza o nome completo da escola.", "Masukkan nama sekolah lengkap.", "Hakerek eskola nia naran kompletu."),
    "age_error": ("Enter an age from 5 to 100.", "Introduza uma idade entre 5 e 100.", "Masukkan umur 5 sampai 100.", "Hakerek tinan entre 5 no 100."),
    "class_error": ("Enter the class.", "Introduza a turma.", "Masukkan kelas.", "Hakerek klase."),
    "room_error": ("Enter the classroom.", "Introduza a sala.", "Masukkan ruang kelas.", "Hakerek sala."),
    "subject_error": ("Teachers must enter the subject they teach.", "O professor deve indicar a disciplina que leciona.", "Guru wajib mengisi mata pelajaran yang diajar.", "Profesór tenke hakerek matéria ne'ebé nia hanorin."),
    "photo_required": ("Choose a profile picture or skip this step.", "Escolha uma imagem de perfil ou ignore este passo.", "Pilih foto profil atau lewati langkah ini.", "Hili foto perfil ka hakat liu pasu ida-ne'e."),
    "photo_limit": ("The profile picture must be an image of 2 MB or less.", "A imagem de perfil deve ter no máximo 2 MB.", "Foto profil harus berupa gambar maksimal 2 MB.", "Foto perfil tenke imajen ho 2 MB ka menus."),
    "profile_photo": ("Profile picture (optional)", "Imagem de perfil (opcional)", "Foto profil (opsional)", "Foto perfil (opsionál)"),
    "choose_photo": ("Choose picture", "Escolher imagem", "Pilih foto", "Hili foto"),
    "skip_photo": ("No photo — use my initials", "Sem foto — usar as minhas iniciais", "Tanpa foto — pakai inisial saya", "Laiha foto — uza ha'u-nia inisiál"),
    "accept_rules": ("I have read and accept the school usage rules", "Li e aceito as regras de utilização da escola", "Saya sudah membaca dan menyetujui aturan penggunaan sekolah", "Ha'u lee ona no simu regra uzu eskola nian"),
    "read_rules": ("Read the rules", "Ler as regras", "Baca aturan", "Lee regra"),
    "rules_required": ("You must accept the school usage rules.", "Tem de aceitar as regras de utilização.", "Anda wajib menyetujui aturan penggunaan sekolah.", "Ita tenke simu regra uzu eskola nian."),
    "identity_note": (
        "Your device has a signed ID. It proves the messages come from this computer, not a person's legal identity.",
        "O seu dispositivo tem um ID assinado. Prova que as mensagens vêm deste computador, não a identidade legal da pessoa.",
        "Perangkat Anda memiliki ID bertanda tangan digital. ID ini membuktikan pesan berasal dari komputer ini, bukan identitas hukum seseorang.",
        "Ita-nia dispozitivu iha ID ho asinatura. Ne'e prova katak mensajen mai husi komputadór ida-ne'e, la'ós ema nia identidade legál.",
    ),
    "version": ("Version", "Versão", "Versi", "Versaun"),
    "edit_profile": ("Edit profile", "Editar perfil", "Ubah profil", "Edita perfil"),
    "cancel": ("Cancel", "Cancelar", "Batal", "Kansela"),
    "close": ("Close", "Fechar", "Tutup", "Taka"),
    "rules_title": ("School usage rules", "Regras de utilização da escola", "Aturan penggunaan sekolah", "Regra uzu eskola nian"),
    "default_rules": (
        "1. Use your real name and correct class details. Pretending to be someone else is forbidden.\n"
        "2. Be polite and respectful. Insults, bullying, threats, hate speech and fake news are forbidden.\n"
        "3. Use the application for learning. Do not send spam, adverts, violent or sexual content.\n"
        "4. Protect privacy: do not share other people's photos, phone numbers or addresses without permission.\n"
        "5. During an exam student chat is disabled. Cheating or sharing answers is forbidden.\n"
        "6. Do your own assignments and exams and send them before the deadline. Late answers are marked.\n"
        "7. Teachers can lock rooms, create groups and send announcements, grades, exams and attendance checks.\n"
        "8. The sender can edit or delete a message during the first 30 minutes.\n"
        "9. Report problems or rule breaking to your teacher or class tutor.\n"
        "10. Breaking these rules can lead to sanctions under the school regulations.",
        "1. Use o seu nome verdadeiro e os dados corretos da turma. É proibido fazer-se passar por outra pessoa.\n"
        "2. Seja educado e respeitoso. Insultos, bullying, ameaças, discurso de ódio e notícias falsas são proibidos.\n"
        "3. Use a aplicação para aprender. Não envie spam, publicidade, conteúdo violento ou sexual.\n"
        "4. Proteja a privacidade: não partilhe fotos, números de telefone ou moradas de outras pessoas sem autorização.\n"
        "5. Durante um exame a conversa dos alunos fica desativada. É proibido copiar ou partilhar respostas.\n"
        "6. Faça os seus trabalhos e exames sozinho e envie-os dentro do prazo. As respostas atrasadas ficam assinaladas.\n"
        "7. O professor pode bloquear salas, criar grupos e enviar anúncios, notas, exames e chamadas.\n"
        "8. Quem enviou pode editar ou eliminar uma mensagem nos primeiros 30 minutos.\n"
        "9. Comunique problemas ou infrações ao professor ou ao diretor de turma.\n"
        "10. O incumprimento destas regras pode levar a sanções segundo o regulamento da escola.",
        "1. Gunakan nama asli dan data kelas yang benar. Dilarang menyamar sebagai orang lain.\n"
        "2. Gunakan bahasa yang sopan dan saling menghormati. Dilarang menghina, merundung (bullying), mengancam, ujaran kebencian, dan hoaks.\n"
        "3. Gunakan aplikasi untuk kegiatan belajar. Jangan mengirim spam, iklan, konten kekerasan atau pornografi.\n"
        "4. Jaga privasi: jangan membagikan foto, nomor telepon, atau alamat orang lain tanpa izin.\n"
        "5. Selama ujian, chat antar siswa dinonaktifkan. Dilarang menyontek atau berbagi jawaban.\n"
        "6. Kerjakan tugas dan ujian sendiri dan kirim sebelum batas waktu. Jawaban yang terlambat akan ditandai.\n"
        "7. Guru dapat mengunci ruang chat, membuat grup, serta mengirim pengumuman, nilai, ujian, dan absensi.\n"
        "8. Pengirim dapat mengedit atau menghapus pesan dalam 30 menit pertama.\n"
        "9. Laporkan masalah atau pelanggaran kepada guru atau wali kelas.\n"
        "10. Pelanggaran aturan dapat dikenai sanksi sesuai tata tertib sekolah.",
        "1. Uza ita-nia naran loloos no dadus klase ne'ebé loos. Labele finje hanesan ema seluk.\n"
        "2. Ko'alia ho edukasaun no respeitu. Labele insulta, halo bullying, ameasa ka fahe notísia falsu.\n"
        "3. Uza aplikasaun ba aprende. Labele haruka spam, anúnsiu, konteúdu violentu ka seksuál.\n"
        "4. Proteje privasidade: labele fahe ema seluk nia foto, númeru telefone ka hela-fatin se la iha autorizasaun.\n"
        "5. Durante ezame, chat estudante sira-nian taka. Labele kopia ka fahe resposta.\n"
        "6. Halo ita-nia tarefa no ezame rasik no haruka molok prazu remata. Resposta tardi sei iha marka.\n"
        "7. Profesór bele xave sala, kria grupu no haruka anúnsiu, nota, ezame no prezensa.\n"
        "8. Ema ne'ebé haruka bele edita ka hamoos mensajen iha minutu 30 dahuluk.\n"
        "9. Relata problema ka violasaun ba profesór ka diretór klase.\n"
        "10. Se la kumpre regra hirak-ne'e bele hetan sansaun tuir regulamentu eskola.",
    ),
    # Shell -----------------------------------------------------------------
    "nav_chat": ("Chat", "Conversas", "Chat", "Chat"),
    "nav_exams": ("Exams & Tasks", "Exames e Trabalhos", "Ujian & Tugas", "Ezame no Tarefa"),
    "nav_attendance": ("Attendance", "Presenças", "Absensi", "Prezensa"),
    "nav_rules": ("Rules", "Regras", "Aturan", "Regra"),
    "nav_network": ("Network", "Rede", "Jaringan", "Rede"),
    "nav_settings": ("Settings", "Definições", "Pengaturan", "Konfigurasaun"),
    "online": ("online", "online", "online", "online"),
    "clear_notifications": ("Reset notification counter", "Repor contador de notificações", "Atur ulang jumlah notifikasi", "Hamoos kontadór notifikasaun"),
    "set_status": ("Set status", "Definir estado", "Buat status", "Halo status"),
    "about": ("About", "Sobre", "Tentang", "Kona-ba"),
    "logout": ("Log out", "Terminar sessão", "Keluar akun", "Sai husi konta"),
    "quit": ("Quit", "Sair", "Tutup aplikasi", "Taka aplikasaun"),
    "connecting": ("Searching for users on the network…", "A procurar utilizadores na rede…", "Mencari pengguna di jaringan…", "Buka hela utilizadór iha rede…"),
    "disconnected": ("Not connected", "Sem ligação", "Tidak terhubung", "La konektadu"),
    "port_in_use": (
        "Port 45901 may already be used by another copy of Eduka-Konekta.",
        "A porta 45901 pode já estar a ser usada por outra cópia do Eduka-Konekta.",
        "Port 45901 mungkin sedang dipakai oleh Eduka-Konekta lain yang sudah terbuka.",
        "Porta 45901 karik uza hela husi Eduka-Konekta seluk ne'ebé loke hela.",
    ),
    "no_network": ("No active network. Connect Wi-Fi or a LAN cable.", "Nenhuma rede ativa. Ligue o Wi-Fi ou um cabo LAN.", "Tidak ada jaringan aktif. Sambungkan Wi-Fi atau kabel LAN.", "Laiha rede ativu. Konekta Wi-Fi ka kabu LAN."),
    "via_relay": ("via relay", "via retransmissão", "lewat relay", "liuhusi relay"),
    "local_ip": ("My IP", "O meu IP", "IP saya", "Ha'u-nia IP"),
    # Rooms -----------------------------------------------------------------
    "rooms": ("ROOMS", "SALAS", "RUANG", "SALA"),
    "groups": ("GROUPS", "GRUPOS", "GRUP", "GRUPU"),
    "direct_chats": ("PRIVATE CHATS", "CONVERSAS PRIVADAS", "CHAT PRIBADI", "CHAT PRIVADU"),
    "teacher_tools": ("TEACHER TOOLS", "FERRAMENTAS DO PROFESSOR", "ALAT GURU", "FERRAMENTA PROFESÓR"),
    "all_schools": ("General Lobby", "Átrio Geral", "Lobi Umum", "Lobi Jerál"),
    "broadcasts": ("Announcements", "Anúncios", "Pengumuman", "Anúnsiu"),
    "my_school": ("Study Forum", "Fórum de Estudo", "Forum Belajar", "Fórum Aprende"),
    "my_class": ("My Class", "A Minha Turma", "Kelas Saya", "Ha'u-nia Klase"),
    "teachers": ("Teachers' Room", "Sala dos Professores", "Ruang Guru", "Sala Profesór"),
    "all_schools_hint": ("Friendly chat for everyone online at school", "Conversa descontraída para todos online na escola", "Obrolan santai untuk semua yang online di sekolah", "Ko'alia livre ba ema hotu ne'ebé online iha eskola"),
    "broadcasts_hint": ("Official announcements from teachers — students can read only", "Anúncios oficiais dos professores — os alunos só podem ler", "Pengumuman resmi dari guru — siswa hanya dapat membaca", "Anúnsiu ofisiál husi profesór — estudante bele lee de'it"),
    "my_school_hint": ("Questions and discussion about lessons across all classes", "Perguntas e discussão sobre as aulas de todas as turmas", "Tanya jawab dan diskusi pelajaran untuk semua kelas", "Pergunta no diskusaun kona-ba lisaun ba klase hotu"),
    "my_class_hint": ("Only students and teachers of your class and classroom", "Apenas alunos e professores da sua turma e sala", "Hanya siswa dan guru dari kelas dan ruang Anda", "Estudante no profesór husi ita-nia klase no sala de'it"),
    "teachers_hint": ("Private room for teachers only", "Sala reservada apenas a professores", "Ruang khusus guru", "Sala espesiál ba profesór de'it"),
    "direct_chat": ("Private chat", "Conversa privada", "Chat pribadi", "Chat privadu"),
    "group_room": ("Group", "Grupo", "Grup", "Grupu"),
    "members": ("members", "membros", "anggota", "membru"),
    "lock_room": ("Lock room", "Bloquear sala", "Kunci ruang", "Xave sala"),
    "unlock_room": ("Unlock room", "Desbloquear sala", "Buka kunci ruang", "Loke xave sala"),
    "clear_history": ("Clear this room on this computer", "Limpar esta sala neste computador", "Bersihkan ruang ini di komputer ini", "Hamoos sala ida-ne'e iha komputadór ne'e"),
    "message_placeholder": ("Write a message…", "Escreva uma mensagem…", "Tulis pesan…", "Hakerek mensajen…"),
    "send": ("Send", "Enviar", "Kirim", "Haruka"),
    "emoji": ("Emoji", "Emoji", "Emoji", "Emoji"),
    "upload_image": ("Send a photo from a folder or USB", "Enviar foto de uma pasta ou USB", "Kirim foto dari folder atau USB", "Haruka foto husi pasta ka USB"),
    "upload_video": ("Send a video (max. 30 s)", "Enviar vídeo (máx. 30 s)", "Kirim video (maks. 30 detik)", "Haruka vídeu (másimu 30 s)"),
    "upload_audio": ("Send voice or audio (max. 60 s)", "Enviar voz ou áudio (máx. 60 s)", "Kirim suara atau audio (maks. 60 detik)", "Haruka lian ka áudiu (másimu 60 s)"),
    "upload_document": ("Send a document or file (max. 25 MB)", "Enviar documento ou ficheiro (máx. 25 MB)", "Kirim dokumen atau file (maks. 25 MB)", "Haruka dokumentu ka arkivu (másimu 25 MB)"),
    "capture_photo": ("Take a webcam photo and send it", "Tirar foto com a webcam e enviar", "Ambil foto webcam lalu kirim", "Hasai foto ho webcam no haruka"),
    "record_voice": ("Record voice and send it", "Gravar voz e enviar", "Rekam suara lalu kirim", "Grava lian no haruka"),
    "record_video": ("Record webcam video and send it", "Gravar vídeo da webcam e enviar", "Rekam video webcam lalu kirim", "Grava vídeu webcam no haruka"),
    "status_feed": ("STATUS", "ESTADOS", "STATUS", "STATUS"),
    "no_status_updates": ("No status yet. Share what you are learning today!", "Ainda sem estados. Partilhe o que está a aprender hoje!", "Belum ada status. Bagikan apa yang sedang kamu pelajari hari ini!", "Seidauk iha status. Fahe saida mak ita aprende ohin!"),
    "online_directory": ("WHO IS ONLINE", "QUEM ESTÁ ONLINE", "SIAPA YANG ONLINE", "SE MAK ONLINE"),
    "refresh_online": ("Refresh and search again", "Atualizar e procurar novamente", "Segarkan & cari ulang", "Atualiza no buka fali"),
    "refreshing_online": ("Searching all Wi-Fi and LAN networks…", "A procurar em todas as redes Wi-Fi e LAN…", "Mencari di semua jaringan Wi-Fi dan LAN…", "Buka hela iha rede Wi-Fi no LAN hotu…"),
    "search_people": ("Search name or class…", "Procurar nome ou turma…", "Cari nama atau kelas…", "Buka naran ka klase…"),
    "teachers_online": ("TEACHERS", "PROFESSORES", "GURU", "PROFESÓR"),
    "students_online": ("STUDENTS", "ALUNOS", "SISWA", "ESTUDANTE"),
    "no_students_online": ("No students online", "Nenhum aluno online", "Belum ada siswa online", "Seidauk iha estudante online"),
    "no_teachers_online": ("No teachers online", "Nenhum professor online", "Belum ada guru online", "Seidauk iha profesór online"),
    "you": ("you", "você", "Anda", "ita"),
    "connection_direct": ("Direct connection", "Ligação direta", "Koneksi langsung", "Koneksaun diretu"),
    "connection_relay": ("Connected through", "Ligado através de", "Terhubung melalui", "Konekta liuhusi"),
    "broadcast_teacher_only": ("Only teachers can post announcements.", "Apenas professores podem publicar anúncios.", "Hanya guru yang dapat mengirim pengumuman.", "Profesór de'it mak bele haruka anúnsiu."),
    "room_locked_banner": ("This room was locked by {name}. Students can read but not send messages.", "Esta sala foi bloqueada por {name}. Os alunos podem ler, mas não enviar.", "Ruang ini dikunci oleh {name}. Siswa dapat membaca tetapi tidak dapat mengirim pesan.", "Sala ida-ne'e xave husi {name}. Estudante bele lee maibé labele haruka."),
    "exam_lock_banner": ("Exam mode: \"{title}\" is running. You can only message teachers privately.", "Modo exame: \"{title}\" está a decorrer. Só pode escrever em privado aos professores.", "Mode ujian: \"{title}\" sedang berlangsung. Anda hanya dapat mengirim pesan pribadi ke guru.", "Modu ezame: \"{title}\" la'o hela. Ita bele haruka mensajen privadu ba profesór de'it."),
    "room_locked": ("Room locked by the teacher", "Sala bloqueada pelo professor", "Ruang dikunci oleh guru", "Sala xave husi profesór"),
    "room_unlocked": ("Room unlocked by the teacher", "Sala desbloqueada pelo professor", "Kunci ruang dibuka oleh guru", "Profesór loke xave sala"),
    "cannot_send": ("Message not sent", "Mensagem não enviada", "Pesan tidak terkirim", "Mensajen la haruka"),
    "rate_limited": ("You are sending too fast. Wait a few seconds.", "Está a enviar demasiado depressa. Aguarde alguns segundos.", "Anda mengirim terlalu cepat. Tunggu beberapa detik.", "Ita haruka lalais liu. Hein segundu balu."),
    "unknown_user": ("Unknown user", "Utilizador desconhecido", "Pengguna tidak dikenal", "Utilizadór la koñesidu"),
    "announcement": ("Announcement", "Anúncio", "Pengumuman", "Anúnsiu"),
    "grade_received": ("Grade", "Nota", "Nilai", "Nota"),
    "new_message": ("New message", "Nova mensagem", "Pesan baru", "Mensajen foun"),
    "received_image": ("sent a photo", "enviou uma foto", "mengirim foto", "haruka foto"),
    "received_video": ("sent a video", "enviou um vídeo", "mengirim video", "haruka vídeu"),
    "received_audio": ("sent a voice message", "enviou uma mensagem de voz", "mengirim pesan suara", "haruka mensajen lian"),
    "received_document": ("sent a document", "enviou um documento", "mengirim dokumen", "haruka dokumentu"),
    "room_empty": ("No messages yet. Start a friendly, respectful conversation.", "Ainda não há mensagens. Comece uma conversa amigável e respeitosa.", "Belum ada pesan. Mulai percakapan yang ramah dan sopan.", "Seidauk iha mensajen. Hahú konversa ida ho respeitu."),
    "open": ("Open", "Abrir", "Buka", "Loke"),
    "save_as": ("Save as…", "Guardar como…", "Simpan ke…", "Rai iha…"),
    "edited": ("edited", "editada", "diedit", "edita ona"),
    "edit_message": ("Edit", "Editar", "Edit", "Edita"),
    "replace_file": ("Replace file", "Substituir ficheiro", "Ganti file", "Troka arkivu"),
    "delete_message": ("Delete", "Eliminar", "Hapus", "Hamoos"),
    "save_changes": ("Save changes", "Guardar alterações", "Simpan perubahan", "Rai mudansa"),
    "edit_window_expired": ("Messages can only be changed or deleted during the first 30 minutes.", "As mensagens só podem ser alteradas ou eliminadas nos primeiros 30 minutos.", "Pesan hanya dapat diubah atau dihapus dalam 30 menit pertama.", "Mensajen bele muda ka hamoos iha minutu 30 dahuluk de'it."),
    "attachment_error": ("The file cannot be sent", "Não é possível enviar o ficheiro", "File tidak dapat dikirim", "Labele haruka arkivu"),
    "invalid_type": ("This file type is not supported.", "Este tipo de ficheiro não é suportado.", "Jenis file ini tidak didukung.", "Tipu arkivu ida-ne'e la suporta."),
    "image_limit": ("Images must be 10 MB or smaller.", "As imagens devem ter no máximo 10 MB.", "Ukuran gambar maksimal 10 MB.", "Imajen tenke 10 MB ka menus."),
    "video_limit": ("Videos must be 30 seconds or shorter and 25 MB or smaller.", "Os vídeos devem ter no máximo 30 segundos e 25 MB.", "Video maksimal 30 detik dan 25 MB.", "Vídeu tenke segundu 30 ka menus no 25 MB ka menus."),
    "audio_limit": ("Audio must be 60 seconds or shorter and 10 MB or smaller.", "O áudio deve ter no máximo 60 segundos e 10 MB.", "Audio maksimal 60 detik dan 10 MB.", "Áudiu tenke segundu 60 ka menus no 10 MB ka menus."),
    "duration_tool": ("The media length could not be checked. Install FFmpeg and try again.", "Não foi possível verificar a duração. Instale o FFmpeg e tente novamente.", "Durasi media tidak dapat diperiksa. Pasang FFmpeg lalu coba lagi.", "Labele haree durasaun mídia. Instala FFmpeg no koko fali."),
    "document_limit": ("Documents and files must be 25 MB or smaller.", "Documentos e ficheiros devem ter no máximo 25 MB.", "Dokumen dan file maksimal 25 MB.", "Dokumentu no arkivu tenke 25 MB ka menus."),
    "delete_message_confirm": ("Delete this message for everyone?", "Eliminar esta mensagem para todos?", "Hapus pesan ini untuk semua orang?", "Hamoos mensajen ida-ne'e ba ema hotu?"),
    "direct_unavailable": ("This user is no longer online.", "Este utilizador já não está online.", "Pengguna ini sudah tidak online.", "Utilizadór ida-ne'e la online ona."),
    "teacher_online": ("Teacher online", "Professor online", "Guru online", "Profesór online"),
    "friend_online": ("Friend online", "Amigo online", "Teman online", "Belun online"),
    "status_image": ("Image status", "Estado com imagem", "Status gambar", "Status imajen"),
    "status_compose_hint": ("Write something, choose an emotion, or attach one picture.", "Escreva algo, escolha uma emoção ou anexe uma imagem.", "Tulis sesuatu, pilih emosi, atau lampirkan satu gambar.", "Hakerek buat ruma, hili emosaun ka tau imajen ida."),
    "status_placeholder": ("What are you learning today?", "O que está a aprender hoje?", "Apa yang kamu pelajari hari ini?", "Saida mak ita aprende ohin?"),
    "no_emotion": ("No emotion", "Sem emoção", "Tanpa emosi", "Laiha emosaun"),
    "no_status_image": ("No picture selected", "Nenhuma imagem selecionada", "Belum memilih gambar", "Seidauk hili imajen"),
    "choose_status_image": ("Choose a picture", "Escolher imagem", "Pilih gambar", "Hili imajen"),
    "clear_status": ("Remove status", "Remover estado", "Hapus status", "Hamoos status"),
    "publish_status": ("Post status", "Publicar estado", "Kirim status", "Haruka status"),
    "open_status_image": ("Open status picture", "Abrir imagem do estado", "Buka gambar status", "Loke imajen status"),
    "new_status": ("New status", "Novo estado", "Status baru", "Status foun"),
    "new_group": ("New group", "Novo grupo", "Grup baru", "Grupu foun"),
    "teacher_only": ("This function is available only to teachers.", "Esta função está disponível apenas para professores.", "Fungsi ini hanya tersedia untuk guru.", "Funsaun ida-ne'e ba profesór de'it."),
    "nobody_online": ("Nobody else is online yet.", "Ainda não há mais ninguém online.", "Belum ada pengguna lain yang online.", "Seidauk iha ema seluk online."),
    "group_name": ("Group name", "Nome do grupo", "Nama grup", "Naran grupu"),
    "group_members": ("Choose the members", "Escolha os membros", "Pilih anggota", "Hili membru sira"),
    "create_group": ("Create group", "Criar grupo", "Buat grup", "Kria grupu"),
    "group_invitation": ("You were added to a group", "Foi adicionado a um grupo", "Anda ditambahkan ke grup", "Ita tama ona ba grupu ida"),
    "broadcast": ("Announcement", "Anúncio", "Pengumuman", "Anúnsiu"),
    "broadcast_title": ("Send an announcement to everyone", "Enviar anúncio a todos", "Kirim pengumuman ke semua", "Haruka anúnsiu ba ema hotu"),
    "broadcast_hint": ("The announcement appears in the Announcements room and as a notification on every computer online.", "O anúncio aparece na sala Anúncios e como notificação em todos os computadores online.", "Pengumuman muncul di ruang Pengumuman dan sebagai notifikasi di semua komputer yang online.", "Anúnsiu sei mosu iha sala Anúnsiu no hanesan notifikasaun iha komputadór hotu ne'ebé online."),
    "send_grade": ("Send grade", "Enviar nota", "Kirim nilai", "Haruka nota"),
    "grade_title": ("Send a grade privately", "Enviar nota em privado", "Kirim nilai secara pribadi", "Haruka nota privadu"),
    "exam_name": ("Exam / assignment", "Exame / trabalho", "Ujian / tugas", "Ezame / tarefa"),
    "score": ("Score", "Nota", "Nilai", "Nota"),
    "notes": ("Teacher note", "Observação do professor", "Catatan guru", "Nota profesór"),
    "recipient": ("Student", "Aluno", "Siswa", "Estudante"),
    "image": ("Image", "Imagem", "Gambar", "Imajen"),
    "video": ("Video", "Vídeo", "Video", "Vídeu"),
    "audio": ("Audio", "Áudio", "Audio", "Áudiu"),
    "document": ("Document or file", "Documento ou ficheiro", "Dokumen atau file", "Dokumentu ka arkivu"),
    "upload_local": ("Choose from computer or USB", "Escolher do computador ou USB", "Pilih dari komputer atau USB", "Hili husi komputadór ka USB"),
    "save": ("Save", "Guardar", "Simpan", "Rai"),
    "select": ("Select", "Selecionar", "Pilih", "Hili"),
    "saved": ("Saved", "Guardado", "Tersimpan", "Rai ona"),
    "media_devices": ("Camera & microphone", "Câmara e microfone", "Kamera & mikrofon", "Kámara no mikrofone"),
    "webcams": ("Webcams found", "Webcams encontradas", "Webcam terdeteksi", "Webcam ne'ebé hetan"),
    "microphones": ("Microphones found", "Microfones encontrados", "Mikrofon terdeteksi", "Mikrofone ne'ebé hetan"),
    "no_webcam": ("No webcam was found.", "Nenhuma webcam encontrada.", "Webcam tidak ditemukan.", "La hetan webcam."),
    "no_microphone": ("No microphone was found.", "Nenhum microfone encontrado.", "Mikrofon tidak ditemukan.", "La hetan mikrofone."),
    "capture_ready": ("FFmpeg recording is ready.", "A gravação com FFmpeg está pronta.", "Perekaman FFmpeg siap digunakan.", "Gravasaun FFmpeg prontu ona."),
    "ffmpeg_missing": ("FFmpeg is not installed; install it to record media.", "O FFmpeg não está instalado; instale-o para gravar.", "FFmpeg belum terpasang; pasang untuk merekam media.", "FFmpeg seidauk instala; instala atu grava mídia."),
    "device_controls_hint": ("Use the camera, microphone and video buttons above the message box to record and send.", "Use os botões de câmara, microfone e vídeo acima da caixa de mensagem para gravar e enviar.", "Gunakan tombol kamera, mikrofon, dan video di atas kotak pesan untuk merekam dan mengirim.", "Uza butaun kámara, mikrofone no vídeu iha kaixa mensajen leten atu grava no haruka."),
    "select_webcam": ("Choose a webcam", "Escolher webcam", "Pilih webcam", "Hili webcam"),
    "capture_failed": ("Recording failed", "A gravação falhou", "Perekaman gagal", "Gravasaun la susesu"),
    "start_recording": ("Start recording", "Iniciar gravação", "Mulai merekam", "Hahú grava"),
    "webcam": ("Webcam", "Webcam", "Webcam", "Webcam"),
    "microphone": ("Microphone", "Microfone", "Mikrofon", "Mikrofone"),
    "video_without_audio": ("Video without sound", "Vídeo sem som", "Video tanpa suara", "Vídeu laiha lian"),
    "recording_seconds": ("Maximum length (seconds)", "Duração máxima (segundos)", "Durasi maksimal (detik)", "Durasaun másimu (segundu)"),
    "stop_and_send": ("Stop and send", "Parar e enviar", "Berhenti dan kirim", "Para no haruka"),
    "recording": ("Recording", "A gravar", "Merekam", "Grava hela"),
    "seconds": ("seconds", "segundos", "detik", "segundu"),
    "manual_ip_title": ("Connect by IP address", "Ligar por endereço IP", "Hubungkan lewat alamat IP", "Konekta liuhusi enderesu IP"),
    "manual_ip_text": (
        "Enter the IP address of another computer running Eduka-Konekta (for example the teacher's computer). You can see it on that computer's Network page. The address is remembered.",
        "Introduza o endereço IP de outro computador com o Eduka-Konekta (por exemplo o do professor). Pode vê-lo na página Rede desse computador. O endereço fica memorizado.",
        "Masukkan alamat IP komputer lain yang menjalankan Eduka-Konekta (misalnya komputer guru). Alamat dapat dilihat di halaman Jaringan komputer tersebut. Alamat akan diingat.",
        "Hakerek enderesu IP husi komputadór seluk ne'ebé uza Eduka-Konekta (ezemplu komputadór profesór nian). Ita bele haree iha pájina Rede komputadór ne'e nian. Enderesu sei rai.",
    ),
    "connect": ("Connect", "Ligar", "Hubungkan", "Konekta"),
    "invalid_ip": ("Invalid IP address", "Endereço IP inválido", "Alamat IP tidak valid", "Enderesu IP la loos"),
    "connecting_to": ("Connecting to {ip}… The user appears in the online list when the connection succeeds.", "A ligar a {ip}… O utilizador aparece na lista quando a ligação resultar.", "Menghubungkan ke {ip}… Pengguna akan muncul di daftar online jika berhasil.", "Konekta hela ba {ip}… Utilizadór sei mosu iha lista online se konsege."),
    "about_body": (
        "A lightweight school application for chat, exams, assignments and attendance. It works peer-to-peer over the school network without internet or a central server.",
        "Aplicação escolar leve para conversas, exames, trabalhos e presenças. Funciona ponto a ponto na rede da escola, sem internet nem servidor central.",
        "Aplikasi sekolah ringan untuk chat, ujian, tugas, dan absensi. Bekerja langsung antarkomputer melalui jaringan sekolah tanpa internet dan tanpa server pusat.",
        "Aplikasaun eskola kmaan ba chat, ezame, tarefa no prezensa. Funsiona diretamente entre komputadór liuhusi rede eskola, laiha internet no laiha servidór sentrál.",
    ),
    "session_privacy": (
        "Chat messages, status, groups and received chat files are erased when the application closes. Your profile stays signed in until you log out.",
        "Mensagens, estados, grupos e ficheiros recebidos na conversa são apagados ao fechar a aplicação. O perfil continua ativo até terminar sessão.",
        "Pesan chat, status, grup, dan file chat yang diterima dihapus saat aplikasi ditutup. Profil tetap masuk sampai Anda keluar akun.",
        "Mensajen chat, status, grupu no arkivu chat ne'ebé simu sei hamoos bainhira taka aplikasaun. Perfil sei tama nafatin to'o ita sai husi konta.",
    ),
    "network_warning": (
        "Use only on a trusted school network. Messages are digitally signed but not end-to-end encrypted.",
        "Use apenas numa rede escolar de confiança. As mensagens são assinadas digitalmente, mas não têm encriptação ponta a ponta.",
        "Gunakan hanya di jaringan sekolah tepercaya. Pesan ditandatangani secara digital tetapi belum dienkripsi end-to-end.",
        "Uza de'it iha rede eskola konfiavel. Mensajen iha asinatura dijitál maibé seidauk enkriptadu end-to-end.",
    ),
    "identity": ("Device ID", "ID do dispositivo", "ID perangkat", "ID dispozitivu"),
    "developed_by": ("Hugo Moniz do Rego\nSTI – Digitalização & Mídia – MCAS & Grupo IDEA",) * 4,
    "copyright": ("Made for education in Timor-Leste", "Feito para a educação em Timor-Leste", "Dibuat untuk pendidikan di Timor-Leste", "Halo ba edukasaun iha Timor-Leste"),
    "logout_confirm": ("Log out of Eduka-Konekta?", "Terminar sessão no Eduka-Konekta?", "Keluar dari Eduka-Konekta?", "Sai husi Eduka-Konekta?"),
    "logout_detail": (
        "Your saved profile is removed from this computer. Exam and attendance records are kept. Closing the window without logging out keeps you signed in.",
        "O perfil guardado é removido deste computador. Os registos de exames e presenças são mantidos. Fechar a janela sem terminar sessão mantém a sessão ativa.",
        "Profil tersimpan dihapus dari komputer ini. Data ujian dan absensi tetap disimpan. Menutup jendela tanpa keluar akun akan membuat Anda tetap masuk.",
        "Perfil ne'ebé rai sei hamoos husi komputadór ne'e. Rejistu ezame no prezensa sei rai nafatin. Se taka janela de'it, ita sei tama nafatin.",
    ),
    "confirm_clear": ("Clear this room's history on this computer?", "Limpar o histórico desta sala neste computador?", "Hapus riwayat ruang ini di komputer ini?", "Hamoos istória sala ne'e iha komputadór ida-ne'e?"),
    "clear": ("Clear", "Limpar", "Bersihkan", "Hamoos"),
    "delete": ("Delete", "Eliminar", "Hapus", "Hamoos"),
    # Exams -------------------------------------------------------------------
    "exams_title": ("Exams & Assignments", "Exames e Trabalhos", "Ujian & Tugas", "Ezame no Tarefa"),
    "exams_subtitle_teacher": (
        "Create an exam, send it to a class, receive answers and return grades.",
        "Crie um exame, envie-o a uma turma, receba as respostas e devolva as notas.",
        "Buat ujian, kirim ke kelas, terima jawaban, dan kembalikan nilai.",
        "Kria ezame, haruka ba klase, simu resposta no fó fali nota.",
    ),
    "exams_subtitle_student": (
        "Open an exam, download the questions, answer and send back to your teacher.",
        "Abra um exame, descarregue as perguntas, responda e devolva ao professor.",
        "Buka ujian, unduh soal, kerjakan, lalu kirim kembali ke guru.",
        "Loke ezame, download pergunta, hatán no haruka fali ba profesór.",
    ),
    "create_exam": ("New exam / assignment", "Novo exame / trabalho", "Buat ujian / tugas", "Ezame / tarefa foun"),
    "no_exams_teacher": ("No exams yet. Press \"New exam / assignment\" to start.", "Ainda não há exames. Carregue em \"Novo exame / trabalho\".", "Belum ada ujian. Tekan \"Buat ujian / tugas\" untuk mulai.", "Seidauk iha ezame. Klik \"Ezame / tarefa foun\" atu hahú."),
    "no_exams_student": ("No exams or assignments yet. They appear here when your teacher sends them.", "Ainda não há exames nem trabalhos. Aparecem aqui quando o professor os enviar.", "Belum ada ujian atau tugas. Akan muncul di sini saat guru mengirimnya.", "Seidauk iha ezame ka tarefa. Sei mosu iha ne'e bainhira profesór haruka."),
    "kind_exam": ("Exam", "Exame", "Ujian", "Ezame"),
    "kind_assignment": ("Assignment", "Trabalho", "Tugas", "Tarefa"),
    "kind_quiz": ("Quiz", "Quiz", "Kuis", "Kuis"),
    "state_open": ("Open", "Aberto", "Dibuka", "Loke"),
    "state_ended": ("Time up", "Tempo esgotado", "Waktu habis", "Tempu remata"),
    "state_closed": ("Closed", "Fechado", "Ditutup", "Taka ona"),
    "target_all": ("All students", "Todos os alunos", "Semua siswa", "Estudante hotu"),
    "target_students": ("Selected students", "Alunos escolhidos", "Siswa tertentu", "Estudante ne'ebé hili"),
    "target_class": ("One class", "Uma turma", "Satu kelas", "Klase ida"),
    "answers_count": ("answers", "respostas", "jawaban", "resposta"),
    "received_count": ("received", "recebido", "diterima", "simu"),
    "answer_sent": ("Answer sent", "Resposta enviada", "Jawaban terkirim", "Resposta haruka ona"),
    "answer_received": ("Received by teacher", "Recebida pelo professor", "Diterima guru", "Profesór simu ona"),
    "answer_sent_waiting": ("Sent — waiting for the teacher's confirmation", "Enviada — a aguardar confirmação do professor", "Terkirim — menunggu konfirmasi guru", "Haruka ona — hein konfirmasaun profesór"),
    "answer_queued": ("Saved. It will be sent automatically when the teacher is online.", "Guardada. Será enviada automaticamente quando o professor estiver online.", "Tersimpan. Jawaban dikirim otomatis saat guru online.", "Rai ona. Sei haruka automátiku bainhira profesór online."),
    "select_exam_hint": ("Choose an exam or assignment from the list.", "Escolha um exame ou trabalho da lista.", "Pilih ujian atau tugas dari daftar.", "Hili ezame ka tarefa husi lista."),
    "exam_howto_title": ("How it works", "Como funciona", "Cara kerja", "Oinsá funsiona"),
    "exam_howto_teacher": (
        "1. Press \"New exam / assignment\" and type the questions (multiple choice or essay) and/or attach a question file (PDF, Word…).\n"
        "2. Choose the class and time limit, then publish. Students online receive it at once; the others receive it automatically when they connect.\n"
        "3. Answers arrive here. Multiple choice is graded automatically. Review, give the final score and feedback, and send the result.\n"
        "4. Export the results to CSV (Excel/LibreOffice) or save all answer files to a folder. Records are kept on this computer.",
        "1. Carregue em \"Novo exame / trabalho\" e escreva as perguntas (escolha múltipla ou resposta aberta) e/ou anexe um ficheiro (PDF, Word…).\n"
        "2. Escolha a turma e o tempo limite e publique. Os alunos online recebem logo; os outros recebem automaticamente quando se ligarem.\n"
        "3. As respostas chegam aqui. A escolha múltipla é corrigida automaticamente. Reveja, dê a nota final e o comentário e envie o resultado.\n"
        "4. Exporte os resultados para CSV (Excel/LibreOffice) ou guarde todos os ficheiros de resposta numa pasta. Os registos ficam neste computador.",
        "1. Tekan \"Buat ujian / tugas\", ketik soal (pilihan ganda atau esai) dan/atau lampirkan file soal (PDF, Word…).\n"
        "2. Pilih kelas dan batas waktu, lalu kirim. Siswa yang online langsung menerima; yang lain menerima otomatis saat terhubung.\n"
        "3. Jawaban masuk ke sini. Pilihan ganda dinilai otomatis. Periksa, beri nilai akhir dan catatan, lalu kirim hasilnya.\n"
        "4. Ekspor hasil ke CSV (Excel/LibreOffice) atau simpan semua file jawaban ke folder. Data tersimpan di komputer ini.",
        "1. Klik \"Ezame / tarefa foun\", hakerek pergunta (hili resposta ka esai) no/ka tau arkivu pergunta (PDF, Word…).\n"
        "2. Hili klase no limite tempu, depois haruka. Estudante ne'ebé online simu kedas; seluk simu automátiku bainhira sira konekta.\n"
        "3. Resposta sira to'o iha ne'e. Hili resposta hetan nota automátiku. Haree, fó nota finál no komentáriu, no haruka rezultadu.\n"
        "4. Esporta rezultadu ba CSV (Excel/LibreOffice) ka rai arkivu resposta hotu iha pasta. Rejistu rai iha komputadór ida-ne'e.",
    ),
    "exam_howto_student": (
        "1. Exams from your teacher appear in the list on the left.\n"
        "2. If there is a question file, press \"Download questions\", then open or save it.\n"
        "3. Answer the questions and/or attach your answer file (photo, Word, PDF…).\n"
        "4. Press \"Send answers\". If the teacher is offline your answer is sent automatically later.\n"
        "5. Your score and the teacher's feedback appear here when they are returned.",
        "1. Os exames do professor aparecem na lista à esquerda.\n"
        "2. Se houver um ficheiro de perguntas, carregue em \"Descarregar perguntas\" e abra-o ou guarde-o.\n"
        "3. Responda às perguntas e/ou anexe o ficheiro de resposta (foto, Word, PDF…).\n"
        "4. Carregue em \"Enviar respostas\". Se o professor estiver offline, a resposta é enviada automaticamente mais tarde.\n"
        "5. A nota e o comentário do professor aparecem aqui quando forem devolvidos.",
        "1. Ujian dari guru muncul di daftar sebelah kiri.\n"
        "2. Jika ada file soal, tekan \"Unduh soal\", lalu buka atau simpan.\n"
        "3. Jawab soal dan/atau lampirkan file jawaban (foto, Word, PDF…).\n"
        "4. Tekan \"Kirim jawaban\". Jika guru sedang offline, jawaban dikirim otomatis nanti.\n"
        "5. Nilai dan catatan guru muncul di sini setelah dikembalikan.",
        "1. Ezame husi profesór mosu iha lista karuk.\n"
        "2. Se iha arkivu pergunta, klik \"Download pergunta\", depois loke ka rai.\n"
        "3. Hatán pergunta sira no/ka tau arkivu resposta (foto, Word, PDF…).\n"
        "4. Klik \"Haruka resposta\". Se profesór offline, resposta sei haruka automátiku depois.\n"
        "5. Ita-nia nota no komentáriu profesór sei mosu iha ne'e bainhira nia fó fali.",
    ),
    "exam_mode": ("Exam mode", "Modo exame", "Mode ujian", "Modu ezame"),
    "minutes": ("minutes", "minutos", "menit", "minutu"),
    "no_time_limit": ("no time limit", "sem limite de tempo", "tanpa batas waktu", "laiha limite tempu"),
    "stat_received": ("received the exam", "receberam o exame", "sudah menerima soal", "simu ona ezame"),
    "stat_answered": ("answers", "respostas", "jawaban masuk", "resposta tama"),
    "stat_graded": ("graded", "classificadas", "sudah dinilai", "hetan nota ona"),
    "stat_online": ("target students online", "alunos-alvo online", "siswa sasaran online", "estudante alvu online"),
    "resend_exam": ("Send again", "Enviar novamente", "Kirim ulang", "Haruka fali"),
    "export_csv": ("Export CSV", "Exportar CSV", "Ekspor CSV", "Esporta CSV"),
    "save_answer_files": ("Save answer files", "Guardar ficheiros de resposta", "Simpan file jawaban", "Rai arkivu resposta"),
    "close_exam": ("Close", "Fechar", "Tutup", "Taka"),
    "open_question_file": ("Question file", "Ficheiro de perguntas", "File soal", "Arkivu pergunta"),
    "submissions": ("ANSWERS RECEIVED", "RESPOSTAS RECEBIDAS", "JAWABAN MASUK", "RESPOSTA NE'EBÉ SIMU"),
    "no_submissions": ("No answers yet.", "Ainda não há respostas.", "Belum ada jawaban.", "Seidauk iha resposta."),
    "late": ("Late", "Atrasado", "Terlambat", "Tardi"),
    "auto_score": ("Multiple choice", "Escolha múltipla", "Pilihan ganda", "Hili resposta"),
    "review_and_grade": ("Review & grade", "Rever e classificar", "Periksa & nilai", "Haree no fó nota"),
    "not_submitted_online": ("ONLINE BUT NOT SUBMITTED YET", "ONLINE MAS AINDA SEM RESPOSTA", "ONLINE TETAPI BELUM MENGUMPULKAN", "ONLINE MAIBÉ SEIDAUK HARUKA"),
    "your_score": ("Your score", "A sua nota", "Nilai Anda", "Ita-nia nota"),
    "teacher_feedback": ("Teacher feedback", "Comentário do professor", "Catatan guru", "Komentáriu profesór"),
    "download_questions": ("Download questions", "Descarregar perguntas", "Unduh soal", "Download pergunta"),
    "points": ("points", "pontos", "poin", "pontu"),
    "no_answer_file": ("No answer file attached (optional)", "Nenhum ficheiro de resposta (opcional)", "Belum ada file jawaban (opsional)", "Seidauk iha arkivu resposta (opsionál)"),
    "attach_answer_file": ("Attach answer file", "Anexar ficheiro de resposta", "Lampirkan file jawaban", "Tau arkivu resposta"),
    "not_submitted": ("Not submitted yet", "Ainda não enviado", "Belum dikirim", "Seidauk haruka"),
    "save_draft": ("Save draft", "Guardar rascunho", "Simpan draf", "Rai rascunho"),
    "resubmit": ("Send again (replace)", "Enviar novamente (substituir)", "Kirim ulang (ganti)", "Haruka fali (troka)"),
    "submit_answers": ("Send answers", "Enviar respostas", "Kirim jawaban", "Haruka resposta"),
    "draft_saved": ("Draft saved on this computer", "Rascunho guardado neste computador", "Draf tersimpan di komputer ini", "Rascunho rai ona iha komputadór ida-ne'e"),
    "download_requested": ("Downloading the question file from the teacher…", "A descarregar o ficheiro de perguntas do professor…", "Mengunduh file soal dari guru…", "Download hela arkivu pergunta husi profesór…"),
    "teacher_offline": ("The teacher is not online. Try again when the teacher's computer is connected.", "O professor não está online. Tente de novo quando o computador do professor estiver ligado.", "Guru sedang tidak online. Coba lagi saat komputer guru terhubung.", "Profesór la online. Koko fali bainhira profesór nia komputadór konekta."),
    "unanswered_warning": ("{count} question(s) have no answer.", "{count} pergunta(s) sem resposta.", "{count} soal belum dijawab.", "Pergunta {count} seidauk iha resposta."),
    "submit_confirm_detail": ("You can send again before the exam closes; the teacher keeps your latest answer.", "Pode enviar de novo antes do fecho; o professor fica com a última resposta.", "Anda masih bisa mengirim ulang sebelum ujian ditutup; guru menyimpan jawaban terakhir.", "Ita bele haruka fali molok ezame taka; profesór rai resposta ikus."),
    "empty_submission": ("Answer at least one question or attach an answer file.", "Responda pelo menos a uma pergunta ou anexe um ficheiro.", "Jawab minimal satu soal atau lampirkan file jawaban.", "Hatán pelumenus pergunta ida ka tau arkivu resposta."),
    "submit_confirm": ("Send your answers to the teacher?", "Enviar as respostas ao professor?", "Kirim jawaban ke guru?", "Haruka resposta ba profesór?"),
    "exam_is_closed": ("This exam is closed.", "Este exame está fechado.", "Ujian ini sudah ditutup.", "Ezame ida-ne'e taka ona."),
    "exam_sent_to": ("Sent to {count} student(s) online.", "Enviado a {count} aluno(s) online.", "Dikirim ke {count} siswa yang online.", "Haruka ona ba estudante {count} ne'ebé online."),
    "close_exam_confirm": ("Close this exam?", "Fechar este exame?", "Tutup ujian ini?", "Taka ezame ida-ne'e?"),
    "close_exam_detail": ("Students can no longer send answers and exam mode ends.", "Os alunos deixam de poder enviar respostas e o modo exame termina.", "Siswa tidak dapat mengirim jawaban lagi dan mode ujian berakhir.", "Estudante labele haruka resposta tan no modu ezame remata."),
    "delete_exam_confirm": ("Delete this exam and all its answers?", "Eliminar este exame e todas as respostas?", "Hapus ujian ini beserta semua jawabannya?", "Hamoos ezame ne'e no resposta hotu?"),
    "delete_exam_detail": ("This cannot be undone. Export the results first if you need them.", "Não pode ser desfeito. Exporte primeiro os resultados se precisar deles.", "Tidak dapat dibatalkan. Ekspor hasil terlebih dahulu jika diperlukan.", "Labele fila fali. Esporta rezultadu uluk se presiza."),
    "files_copied": ("{count} file(s) copied to {folder}", "{count} ficheiro(s) copiado(s) para {folder}", "{count} file disalin ke {folder}", "Arkivu {count} kopia ona ba {folder}"),
    "publish_exam": ("Publish", "Publicar", "Kirim ke siswa", "Haruka ba estudante"),
    "exam_kind": ("Type", "Tipo", "Jenis", "Tipu"),
    "exam_title_hint": ("e.g. Mathematics mid-term test", "ex.: Teste intermédio de Matemática", "mis. Ulangan Tengah Semester Matematika", "ez.: Teste Matemátika semestre klaran"),
    "exam_title": ("Title", "Título", "Judul", "Títulu"),
    "instructions": ("Instructions for students", "Instruções para os alunos", "Petunjuk untuk siswa", "Instrusaun ba estudante"),
    "target": ("Send to", "Enviar para", "Kirim ke", "Haruka ba"),
    "duration_minutes": ("Time limit (minutes, 0 = none)", "Tempo limite (minutos, 0 = sem)", "Batas waktu (menit, 0 = tanpa)", "Limite tempu (minutu, 0 = laiha)"),
    "choose_students": ("Choose at least one student", "Escolha pelo menos um aluno", "Pilih minimal satu siswa", "Hili pelumenus estudante ida"),
    "no_question_file": ("No file (optional)", "Sem ficheiro (opcional)", "Tanpa file (opsional)", "Laiha arkivu (opsionál)"),
    "question_file": ("Question file (PDF, Word, image…)", "Ficheiro de perguntas (PDF, Word, imagem…)", "File soal (PDF, Word, gambar…)", "Arkivu pergunta (PDF, Word, imajen…)"),
    "choose_question_file": ("Choose file", "Escolher ficheiro", "Pilih file", "Hili arkivu"),
    "option_lock_chat": ("Exam mode: block student chat until the exam ends", "Modo exame: bloquear a conversa dos alunos até ao fim", "Mode ujian: blokir chat siswa sampai ujian selesai", "Modu ezame: xave chat estudante to'o ezame remata"),
    "option_allow_late": ("Accept late answers (marked as late)", "Aceitar respostas atrasadas (assinaladas)", "Terima jawaban terlambat (ditandai terlambat)", "Simu resposta tardi (ho marka tardi)"),
    "option_allow_file": ("Students may attach an answer file", "Os alunos podem anexar um ficheiro de resposta", "Siswa boleh melampirkan file jawaban", "Estudante bele tau arkivu resposta"),
    "exam_rules": ("Rules", "Regras", "Aturan", "Regra"),
    "questions": ("QUESTIONS", "PERGUNTAS", "SOAL", "PERGUNTA"),
    "questions_hint": (
        "Optional. Multiple choice is graded automatically; the correct answer is never sent to students.",
        "Opcional. A escolha múltipla é corrigida automaticamente; a resposta certa nunca é enviada aos alunos.",
        "Opsional. Pilihan ganda dinilai otomatis; kunci jawaban tidak pernah dikirim ke siswa.",
        "Opsionál. Hili resposta hetan nota automátiku; resposta loos nunka haruka ba estudante.",
    ),
    "question_choice": ("Multiple choice", "Escolha múltipla", "Pilihan ganda", "Hili resposta"),
    "question_essay": ("Essay", "Resposta aberta", "Esai", "Esai"),
    "option": ("Option", "Opção", "Pilihan", "Opsaun"),
    "correct_answer": ("Correct answer", "Resposta certa", "Kunci jawaban", "Resposta loos"),
    "add_choice_question": ("Multiple choice", "Escolha múltipla", "Pilihan ganda", "Hili resposta"),
    "add_essay_question": ("Essay", "Resposta aberta", "Esai", "Esai"),
    "question_text_missing": ("Question {number} has no text.", "A pergunta {number} não tem texto.", "Soal nomor {number} belum ada teksnya.", "Pergunta {number} laiha testu."),
    "question_options_missing": ("Question {number} needs at least two options.", "A pergunta {number} precisa de pelo menos duas opções.", "Soal nomor {number} membutuhkan minimal dua pilihan.", "Pergunta {number} presiza pelumenus opsaun rua."),
    "question_correct_missing": ("The correct answer of question {number} is an empty option.", "A resposta certa da pergunta {number} é uma opção vazia.", "Kunci jawaban soal nomor {number} adalah pilihan yang kosong.", "Resposta loos pergunta {number} nian mak opsaun mamuk."),
    "exam_title_missing": ("Enter a title.", "Introduza um título.", "Masukkan judul.", "Hakerek títulu."),
    "exam_content_missing": ("Add instructions, a question file or at least one question.", "Adicione instruções, um ficheiro ou pelo menos uma pergunta.", "Tambahkan petunjuk, file soal, atau minimal satu soal.", "Aumenta instrusaun, arkivu pergunta ka pelumenus pergunta ida."),
    "exam_published": ("Published. Sent now to {count} student(s) online; others receive it when they connect.", "Publicado. Enviado agora a {count} aluno(s) online; os outros recebem quando se ligarem.", "Terkirim ke {count} siswa yang online; siswa lain menerima saat terhubung.", "Haruka ona ba estudante {count} online; seluk sei simu bainhira konekta."),
    "send_result": ("Send result", "Enviar resultado", "Kirim hasil", "Haruka rezultadu"),
    "final_score": ("Final score", "Nota final", "Nilai akhir", "Nota finál"),
    "no_answer": ("(no answer)", "(sem resposta)", "(tidak dijawab)", "(laiha resposta)"),
    "score_missing": ("Enter a score.", "Introduza uma nota.", "Masukkan nilai.", "Hakerek nota."),
    "result_sent": ("Result sent to the student.", "Resultado enviado ao aluno.", "Hasil dikirim ke siswa.", "Rezultadu haruka ona ba estudante."),
    "result_saved_offline": ("Result saved. The student is offline; send it again later from this dialog.", "Resultado guardado. O aluno está offline; envie de novo mais tarde.", "Hasil tersimpan. Siswa sedang offline; kirim ulang nanti dari jendela ini.", "Rezultadu rai ona. Estudante offline; haruka fali depois."),
    "new_exam": ("New exam / assignment", "Novo exame / trabalho", "Ujian / tugas baru", "Ezame / tarefa foun"),
    "exam_closed": ("Exam closed", "Exame fechado", "Ujian ditutup", "Ezame taka ona"),
    "exam_file_ready": ("Question file downloaded", "Ficheiro de perguntas descarregado", "File soal berhasil diunduh", "Arkivu pergunta download ona"),
    "new_submission": ("New answer received", "Nova resposta recebida", "Jawaban baru masuk", "Resposta foun tama"),
    "submission_received": ("The teacher received your answer", "O professor recebeu a sua resposta", "Guru sudah menerima jawaban Anda", "Profesór simu ona ita-nia resposta"),
    "result_received": ("Your result has arrived", "Chegou o seu resultado", "Nilai Anda sudah keluar", "Ita-nia rezultadu to'o ona"),
    # Attendance --------------------------------------------------------------
    "attendance": ("Attendance", "Presenças", "Absensi", "Prezensa"),
    "attendance_title": ("Attendance", "Presenças", "Absensi", "Prezensa"),
    "attendance_subtitle_teacher": ("Start a roll call; students confirm with one click. Export the list to CSV.", "Inicie a chamada; os alunos confirmam com um clique. Exporte a lista para CSV.", "Mulai absensi; siswa cukup menekan satu tombol. Ekspor daftar ke CSV.", "Hahú prezensa; estudante klik dala ida de'it. Esporta lista ba CSV."),
    "attendance_subtitle_student": ("When your teacher starts a roll call, press \"I am present\".", "Quando o professor iniciar a chamada, carregue em \"Estou presente\".", "Saat guru memulai absensi, tekan \"Saya hadir\".", "Bainhira profesór hahú prezensa, klik \"Ha'u prezente\"."),
    "start_attendance": ("Start attendance", "Iniciar chamada", "Mulai absensi", "Hahú prezensa"),
    "no_attendance_teacher": ("No roll calls yet.", "Ainda não há chamadas.", "Belum ada absensi.", "Seidauk iha prezensa."),
    "no_attendance_student": ("No attendance requests yet.", "Ainda não há pedidos de presença.", "Belum ada permintaan absensi.", "Seidauk iha pedidu prezensa."),
    "close_attendance": ("Close", "Fechar", "Tutup", "Taka"),
    "present": ("present", "presentes", "hadir", "prezente"),
    "online_now": ("online now", "online agora", "online sekarang", "online agora"),
    "waiting_for": ("Waiting for", "A aguardar", "Menunggu", "Hein"),
    "attendance_recorded": ("Recorded", "Registado", "Tercatat", "Rejista ona"),
    "attendance_sending": ("Sending…", "A enviar…", "Mengirim…", "Haruka hela…"),
    "i_am_present": ("I am present", "Estou presente", "Saya hadir", "Ha'u prezente"),
    "start": ("Start", "Iniciar", "Mulai", "Hahú"),
    "attendance_name": ("Name", "Nome", "Nama", "Naran"),
    "attendance_class_hint": ("Leave the class empty to ask every student online.", "Deixe a turma vazia para pedir a todos os alunos online.", "Kosongkan kelas untuk meminta semua siswa yang online.", "Husik klase mamuk atu husu estudante hotu ne'ebé online."),
    "open_minutes": ("Open for (minutes)", "Aberta durante (minutos)", "Dibuka selama (menit)", "Loke durante (minutu)"),
    "attendance_started": ("Attendance started. Sent to {count} student(s).", "Chamada iniciada. Enviada a {count} aluno(s).", "Absensi dimulai. Dikirim ke {count} siswa.", "Prezensa hahú ona. Haruka ba estudante {count}."),
    "attendance_request": ("Attendance check", "Chamada", "Absensi", "Prezensa"),
    # Rules -------------------------------------------------------------------
    "rules_subtitle": ("Rules for using Eduka-Konekta at school.", "Regras de utilização do Eduka-Konekta na escola.", "Aturan penggunaan Eduka-Konekta di sekolah.", "Regra uzu Eduka-Konekta iha eskola."),
    "school_rules": ("Rules from the school", "Regras da escola", "Aturan dari sekolah", "Regra husi eskola"),
    "enforced_rules": ("Applied automatically", "Aplicado automaticamente", "Diterapkan otomatis", "Aplika automátiku"),
    "enforced_rules_body": (
        "• A word filter masks offensive words (configurable in Settings).\n"
        "• Anti-spam: at most 6 messages every 10 seconds.\n"
        "• Only teachers can post in Announcements and the Teachers' Room.\n"
        "• Teachers can lock a room: students can then only read.\n"
        "• Exam mode: while an exam runs, students can only message teachers privately and messages from other students are hidden.\n"
        "• Every message is digitally signed with the device ID.",
        "• Um filtro esconde palavras ofensivas (configurável em Definições).\n"
        "• Anti-spam: no máximo 6 mensagens a cada 10 segundos.\n"
        "• Só os professores podem publicar em Anúncios e na Sala dos Professores.\n"
        "• O professor pode bloquear uma sala: os alunos passam a poder apenas ler.\n"
        "• Modo exame: durante um exame, os alunos só podem escrever em privado aos professores e as mensagens de outros alunos ficam ocultas.\n"
        "• Cada mensagem é assinada digitalmente com o ID do dispositivo.",
        "• Filter kata menyamarkan kata-kata kasar (dapat diatur di Pengaturan).\n"
        "• Anti-spam: maksimal 6 pesan setiap 10 detik.\n"
        "• Hanya guru yang dapat mengirim di Pengumuman dan Ruang Guru.\n"
        "• Guru dapat mengunci ruang: siswa hanya dapat membaca.\n"
        "• Mode ujian: selama ujian berlangsung, siswa hanya dapat mengirim pesan pribadi ke guru dan pesan dari siswa lain disembunyikan.\n"
        "• Setiap pesan ditandatangani secara digital dengan ID perangkat.",
        "• Filtru liafuan subar liafuan aat (bele muda iha Konfigurasaun).\n"
        "• Anti-spam: másimu mensajen 6 iha segundu 10 ida-idak.\n"
        "• Profesór de'it mak bele haruka iha Anúnsiu no Sala Profesór.\n"
        "• Profesór bele xave sala: estudante bele lee de'it.\n"
        "• Modu ezame: durante ezame, estudante bele haruka mensajen privadu ba profesór de'it no mensajen husi estudante seluk subar.\n"
        "• Mensajen hotu iha asinatura dijitál ho ID dispozitivu.",
    ),
    "edit_school_rules": ("School rules (teacher)", "Regras da escola (professor)", "Aturan sekolah (guru)", "Regra eskola (profesór)"),
    "edit_school_rules_hint": (
        "Write your school's own rules. They are sent to every computer online now and to others when they connect.",
        "Escreva as regras próprias da escola. São enviadas a todos os computadores online e aos outros quando se ligarem.",
        "Tulis aturan khusus sekolah Anda. Aturan dikirim ke semua komputer yang online sekarang dan ke yang lain saat terhubung.",
        "Hakerek eskola nia regra rasik. Sei haruka ba komputadór hotu ne'ebé online agora no ba seluk bainhira sira konekta.",
    ),
    "publish_rules": ("Publish rules", "Publicar regras", "Publikasikan aturan", "Publika regra"),
    "rules_empty": ("Write the rules first.", "Escreva primeiro as regras.", "Tulis aturannya terlebih dahulu.", "Hakerek regra uluk."),
    "rules_published": ("Rules published to the school.", "Regras publicadas na escola.", "Aturan dipublikasikan ke sekolah.", "Regra publika ona ba eskola."),
    "rules_updated": ("School rules updated", "Regras da escola atualizadas", "Aturan sekolah diperbarui", "Regra eskola atualiza ona"),
    # Network -----------------------------------------------------------------
    "network_title": ("Network & connection", "Rede e ligação", "Jaringan & koneksi", "Rede no koneksaun"),
    "network_subtitle": ("See how this computer is connected and fix problems finding other users.", "Veja como este computador está ligado e resolva problemas ao encontrar utilizadores.", "Lihat koneksi komputer ini dan atasi masalah saat pengguna lain tidak ditemukan.", "Haree oinsá komputadór ne'e konekta no hadi'a problema atu hetan utilizadór seluk."),
    "connect_ip": ("Connect IP", "Ligar IP", "Hubungkan IP", "Konekta IP"),
    "stat_direct": ("direct connections", "ligações diretas", "koneksi langsung", "koneksaun diretu"),
    "stat_relayed": ("users via relay", "utilizadores via retransmissão", "pengguna lewat relay", "utilizadór liuhusi relay"),
    "stat_interfaces": ("active networks", "redes ativas", "jaringan aktif", "rede ativu"),
    "stat_port": ("TCP port", "porta TCP", "port TCP", "porta TCP"),
    "my_connections": ("This computer", "Este computador", "Komputer ini", "Komputadór ida-ne'e"),
    "iface_wifi": ("Wi-Fi", "Wi-Fi", "Wi-Fi", "Wi-Fi"),
    "iface_ethernet": ("LAN cable", "Cabo LAN", "Kabel LAN", "Kabu LAN"),
    "iface_other": ("Other", "Outra", "Lainnya", "Seluk"),
    "copy": ("Copy", "Copiar", "Salin", "Kopia"),
    "copied": ("Copied", "Copiado", "Disalin", "Kopia ona"),
    "discovery_on": ("Automatic discovery active (multicast, broadcast, subnet scan and relay)", "Descoberta automática ativa (multicast, broadcast, varrimento da sub-rede e retransmissão)", "Pencarian otomatis aktif (multicast, broadcast, pemindaian subnet, dan relay)", "Buka automátiku ativu (multicast, broadcast, skaneia subrede no relay)"),
    "discovery_off": ("Discovery port 45900 is unavailable; scanning and manual IP still work", "A porta 45900 não está disponível; o varrimento e o IP manual continuam a funcionar", "Port 45900 tidak tersedia; pemindaian dan IP manual tetap berfungsi", "Porta 45900 la disponivel; skaneia no IP manuál funsiona nafatin"),
    "last_scan": ("last network scan", "último varrimento", "pemindaian terakhir", "skaneia ikus"),
    "connected_users": ("Connected users", "Utilizadores ligados", "Pengguna terhubung", "Utilizadór konektadu"),
    "nobody_online_hint": ("Nobody found yet. Check the tips below.", "Ninguém encontrado ainda. Veja as dicas abaixo.", "Belum ada yang ditemukan. Lihat petunjuk di bawah.", "Seidauk hetan ema. Haree dika iha okos."),
    "remembered_addresses": ("Remembered addresses", "Endereços memorizados", "Alamat yang diingat", "Enderesu ne'ebé rai"),
    "forget": ("Forget", "Esquecer", "Lupakan", "Haluha"),
    "wifi_help_title": ("Users not found on Wi-Fi?", "Não encontra utilizadores no Wi-Fi?", "Pengguna lain tidak terlihat di Wi-Fi?", "La hetan utilizadór iha Wi-Fi?"),
    "wifi_help_body": (
        "1. Connect every computer to the same Wi-Fi network and type the school name exactly the same.\n"
        "2. Press \"Refresh and search again\". Eduka-Konekta scans all Wi-Fi and LAN networks automatically.\n"
        "3. Many routers enable \"AP/Client isolation\", which stops Wi-Fi devices from seeing each other. Turn it off in the router, OR connect one computer (for example the teacher's) by LAN cable: it becomes a relay automatically and all Wi-Fi users can talk through it.\n"
        "4. Use \"Connect IP\" with the IP address of the teacher's computer (shown on its Network page). The address is remembered.\n"
        "5. The firewall must allow TCP 45901 and UDP 45900 (the installer opens them automatically for firewalld and ufw).\n"
        "6. Guest Wi-Fi networks usually block devices from talking to each other — use the school network.",
        "1. Ligue todos os computadores à mesma rede Wi-Fi e escreva o nome da escola exatamente igual.\n"
        "2. Carregue em \"Atualizar e procurar novamente\". O Eduka-Konekta procura automaticamente em todas as redes Wi-Fi e LAN.\n"
        "3. Muitos routers ativam o \"isolamento de clientes (AP isolation)\", que impede os dispositivos Wi-Fi de se verem. Desative-o no router OU ligue um computador (por exemplo o do professor) por cabo LAN: passa a retransmitir automaticamente e todos os utilizadores Wi-Fi comunicam através dele.\n"
        "4. Use \"Ligar IP\" com o endereço IP do computador do professor (visível na página Rede). O endereço fica memorizado.\n"
        "5. A firewall deve permitir TCP 45901 e UDP 45900 (o instalador abre-as automaticamente no firewalld e no ufw).\n"
        "6. As redes Wi-Fi de convidados costumam bloquear a comunicação entre dispositivos — use a rede da escola.",
        "1. Sambungkan semua komputer ke jaringan Wi-Fi yang sama dan tulis nama sekolah persis sama.\n"
        "2. Tekan \"Segarkan & cari ulang\". Eduka-Konekta memindai semua jaringan Wi-Fi dan LAN secara otomatis.\n"
        "3. Banyak router mengaktifkan \"AP/Client Isolation\" sehingga perangkat Wi-Fi tidak bisa saling melihat. Matikan opsi itu di pengaturan router, ATAU sambungkan satu komputer (misalnya komputer guru) dengan kabel LAN: komputer itu otomatis menjadi relay sehingga semua pengguna Wi-Fi dapat saling terhubung melaluinya.\n"
        "4. Gunakan \"Hubungkan IP\" dengan alamat IP komputer guru (terlihat di halaman Jaringan komputer guru). Alamat akan diingat.\n"
        "5. Firewall harus mengizinkan TCP 45901 dan UDP 45900 (installer membukanya otomatis untuk firewalld dan ufw).\n"
        "6. Wi-Fi tamu (guest) biasanya memblokir koneksi antarperangkat — gunakan Wi-Fi sekolah.",
        "1. Konekta komputadór hotu ba rede Wi-Fi hanesan no hakerek naran eskola hanesan loos.\n"
        "2. Klik \"Atualiza no buka fali\". Eduka-Konekta skaneia rede Wi-Fi no LAN hotu automátiku.\n"
        "3. Router barak ativa \"AP/Client isolation\", ne'ebé halo dispozitivu Wi-Fi labele haree malu. Dezativa iha router, KA konekta komputadór ida (ezemplu profesór nian) ho kabu LAN: nia sai relay automátiku no utilizadór Wi-Fi hotu bele ko'alia liuhusi nia.\n"
        "4. Uza \"Konekta IP\" ho enderesu IP komputadór profesór nian (haree iha pájina Rede). Enderesu sei rai.\n"
        "5. Firewall tenke permite TCP 45901 no UDP 45900 (instaladór loke automátiku ba firewalld no ufw).\n"
        "6. Wi-Fi ba bainaka (guest) baibain bloke dispozitivu atu ko'alia malu — uza rede eskola nian.",
    ),
    # Settings ----------------------------------------------------------------
    "settings_title": ("Settings", "Definições", "Pengaturan", "Konfigurasaun"),
    "settings_subtitle": ("Adjust Eduka-Konekta to your school and to yourself.", "Ajuste o Eduka-Konekta à sua escola e a si.", "Sesuaikan Eduka-Konekta untuk sekolah dan diri Anda.", "Adapta Eduka-Konekta ba ita-nia eskola no ba ita."),
    "general": ("General", "Geral", "Umum", "Jerál"),
    "language_hint": ("Interface language", "Idioma da interface", "Bahasa tampilan", "Lian ba ekrã"),
    "large_text": ("Large text", "Texto grande", "Teks besar", "Letra boot"),
    "large_text_hint": ("Makes all text 20% larger", "Aumenta todo o texto em 20%", "Memperbesar semua teks 20%", "Halo letra hotu boot liu 20%"),
    "notifications": ("Notifications", "Notificações", "Notifikasi", "Notifikasaun"),
    "desktop_notifications": ("Desktop notifications", "Notificações no ambiente de trabalho", "Notifikasi desktop", "Notifikasaun iha desktop"),
    "desktop_notifications_hint": ("Show a notification when the window is in the background", "Mostrar notificação quando a janela está em segundo plano", "Tampilkan notifikasi saat jendela tidak aktif", "Hatudu notifikasaun bainhira janela la ativu"),
    "notification_sound": ("Notification sound", "Som de notificação", "Suara notifikasi", "Lian notifikasaun"),
    "notification_sound_hint": ("Play a short beep for new messages, exams and announcements", "Tocar um sinal curto para mensagens, exames e anúncios", "Bunyikan beep untuk pesan, ujian, dan pengumuman baru", "Toka lian badak ba mensajen, ezame no anúnsiu foun"),
    "chat_rules": ("Chat rules", "Regras da conversa", "Aturan chat", "Regra chat"),
    "word_filter": ("Offensive word filter", "Filtro de palavras ofensivas", "Filter kata kasar", "Filtru liafuan aat"),
    "word_filter_hint": ("Mask offensive words in messages and status", "Ocultar palavras ofensivas em mensagens e estados", "Samarkan kata kasar pada pesan dan status", "Subar liafuan aat iha mensajen no status"),
    "filter_words": ("Extra blocked words", "Palavras bloqueadas adicionais", "Kata tambahan yang diblokir", "Liafuan tan ne'ebé bloke"),
    "filter_words_hint": ("Separate words with commas", "Separe as palavras com vírgulas", "Pisahkan kata dengan koma", "Fahe liafuan ho vírgula"),
    "default_filter_note": ("{count} common offensive words in Indonesian, Portuguese and English are always included.", "{count} palavras ofensivas comuns em indonésio, português e inglês estão sempre incluídas.", "{count} kata kasar umum dalam bahasa Indonesia, Portugis, dan Inggris sudah termasuk.", "Liafuan aat baibain {count} iha lian Indonézia, Portugés no Inglés inklui ona."),
    "data_privacy": ("Data & privacy", "Dados e privacidade", "Data & privasi", "Dadus no privasidade"),
    "records_note": (
        "Exams, answers, grades, attendance and school rules are kept on this computer so they are not lost. Folder:",
        "Exames, respostas, notas, presenças e regras são guardados neste computador para não se perderem. Pasta:",
        "Ujian, jawaban, nilai, absensi, dan aturan sekolah disimpan di komputer ini agar tidak hilang. Folder:",
        "Ezame, resposta, nota, prezensa no regra eskola rai iha komputadór ida-ne'e atu la lakon. Pasta:",
    ),
    "open_folder": ("Open folder", "Abrir pasta", "Buka folder", "Loke pasta"),
    "account": ("Account", "Conta", "Akun", "Konta"),
}

PT_BR = {
    "sign_in": "Entrar no Eduka-Konekta",
    "no_password": "Sem senha • Sem servidor central • Apenas na rede da escola",
    "full_name_hint": "Nome e sobrenome, ex.: Maria da Silva",
    "student": "Aluno(a)",
    "room": "Sala",
    "continue": "Conectar à rede da escola",
    "profile_error": "Corrija o seguinte",
    "name_error": "Digite nome e sobrenome usando apenas letras.",
    "logout": "Sair da conta",
    "quit": "Fechar",
    "nav_settings": "Configurações",
    "settings_title": "Configurações",
    "connecting": "Procurando usuários na rede…",
    "disconnected": "Sem conexão",
    "no_network": "Nenhuma rede ativa. Conecte o Wi-Fi ou um cabo de rede.",
    "port_in_use": "A porta 45901 pode já estar em uso por outra cópia do Eduka-Konekta.",
    "unknown_user": "Usuário desconhecido",
    "direct_unavailable": "Este usuário não está mais online.",
    "attachment_error": "Não foi possível enviar o arquivo",
    "invalid_type": "Este tipo de arquivo não é suportado.",
    "document_limit": "Documentos e arquivos devem ter no máximo 25 MB.",
    "document": "Documento ou arquivo",
    "upload_document": "Enviar documento ou arquivo (máx. 25 MB)",
    "replace_file": "Substituir arquivo",
    "delete_message": "Excluir",
    "delete": "Excluir",
    "delete_message_confirm": "Excluir esta mensagem para todos?",
    "save_changes": "Salvar alterações",
    "save": "Salvar",
    "saved": "Salvo",
    "save_as": "Salvar como…",
    "media_devices": "Câmera e microfone",
    "connect": "Conectar",
    "connect_ip": "Conectar IP",
    "manual_ip_title": "Conectar por endereço IP",
    "connection_direct": "Conexão direta",
    "connection_relay": "Conectado por meio de",
    "refresh_online": "Atualizar e procurar de novo",
    "search_people": "Buscar nome ou turma…",
    "save_draft": "Salvar rascunho",
    "draft_saved": "Rascunho salvo neste computador",
    "download_questions": "Baixar perguntas",
    "download_requested": "Baixando o arquivo de perguntas do professor…",
    "question_file": "Arquivo de perguntas (PDF, Word, imagem…)",
    "choose_question_file": "Escolher arquivo",
    "no_question_file": "Sem arquivo (opcional)",
    "open_question_file": "Arquivo de perguntas",
    "attach_answer_file": "Anexar arquivo de resposta",
    "no_answer_file": "Nenhum arquivo de resposta (opcional)",
    "save_answer_files": "Salvar arquivos de resposta",
    "files_copied": "{count} arquivo(s) copiado(s) para {folder}",
    "logout_detail": "O perfil salvo é removido deste computador. Os registros de provas e chamadas são mantidos. Fechar a janela sem sair mantém a sessão ativa.",
    "kind_exam": "Prova",
    "nav_exams": "Provas e Trabalhos",
    "exams_title": "Provas e Trabalhos",
    "create_exam": "Nova prova / trabalho",
    "new_exam": "Nova prova / trabalho",
    "exam_mode": "Modo prova",
    "nav_attendance": "Chamada",
    "attendance": "Chamada",
    "attendance_title": "Chamada",
    "start_attendance": "Iniciar chamada",
    "desktop_notifications": "Notificações na área de trabalho",
    "language_hint": "Idioma da interface",
    "records_note": "Provas, respostas, notas, chamadas e regras são salvas neste computador para não se perderem. Pasta:",
    "settings_subtitle": "Ajuste o Eduka-Konekta à sua escola e a você.",
    "local_ip": "Meu IP",
    "my_class": "Minha Turma",
    "my_class_hint": "Apenas alunos e professores da sua turma e sala",
    "copy": "Copiar",
    "message_placeholder": "Digite uma mensagem…",
    "status_placeholder": "O que você está aprendendo hoje?",
    "no_status_updates": "Ainda sem status. Compartilhe o que está aprendendo hoje!",
    "set_status": "Definir status",
    "status_feed": "STATUS",
    "publish_status": "Publicar status",
    "clear_status": "Remover status",
    "new_status": "Novo status",
    "session_privacy": "Mensagens, status, grupos e arquivos recebidos na conversa são apagados ao fechar o aplicativo. O perfil continua conectado até você sair da conta.",
    "upload_local": "Escolher do computador ou pendrive",
    "clear_notifications": "Zerar contador de notificações",
    "you": "você",
    "open_folder": "Abrir pasta",
    "save_as": "Salvar como…",
}

_INDEX = {"en": 0, "pt_PT": 1, "id": 2, "tet": 3}


def _catalog(index: int) -> dict[str, str]:
    return {key: values[index] for key, values in _T.items()}


EN = _catalog(0)
PT = _catalog(1)
ID = _catalog(2)
TET = _catalog(3)
BR = {**PT, **PT_BR}

CATALOGS = {"en": EN, "pt_PT": PT, "pt_BR": BR, "id": ID, "tet": TET}


def tr(language, key):
    """Return a localized string, falling back to International English."""
    return CATALOGS.get(language, EN).get(key, EN.get(key, key))
