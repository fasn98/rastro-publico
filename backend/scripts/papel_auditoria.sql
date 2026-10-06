-- Usuário só de leitura para a API de auditoria (opcional, recomendado).
-- Rode no banco de produção (ferramenta Database do app de coleta, aba SQL), troque a senha
-- e use a string de conexão deste usuário no Secret DATABASE_URL do app de auditoria.
-- A API de auditoria só lê estas quatro tabelas.
CREATE ROLE rastro_auditoria WITH LOGIN PASSWORD 'TROQUE-ESTA-SENHA';
GRANT USAGE ON SCHEMA public TO rastro_auditoria;
GRANT SELECT ON resposta_bruta, payload_bruto, demonstrativo_resposta, conta_demonstrativo
  TO rastro_auditoria;
