#!/usr/bin/env python
import os
import sys
import glob
import time

# Tenta carregar .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')

def listar_videos():
    extensoes = ['*.mp4', '*.MP4', '*.mov', '*.MOV', '*.mkv', '*.MKV', '*.avi']
    arquivos = []
    for ext in extensoes:
        arquivos.extend(glob.glob(ext))
    return sorted(list(set(arquivos)))

def perguntar_gemini_key():
    # Verifica se existe no ambiente (carregado do .env ou sistema)
    key = os.environ.get("GEMINI_API_KEY")
    
    if key:
        print(f"\nℹ️  API Key encontrada no ambiente.")
        return key
    
    print("\n🤖 Deseja ativar a CORREÇÃO DE TEXTO com IA (Google Gemini)?")
    print("   (Isso corrige erros de ortografia e pontuação na legenda)")
    resp = input("   Sim [s] / Não [n] (Default: n): ").strip().lower()
    
    if resp == 's':
        print("\n   Digite sua API Key do Google Gemini (ou cole aqui):")
        key = input("   >>> ").strip()
        if key:
            return key
    return None

def main():
    while True:
        limpar_tela()
        print("=======================================")
        print("   🎬 AUTO VIDEO EDITOR - MENU   ")
        print("=======================================")
        
        videos = listar_videos()
        if not videos:
            print("\n⚠️  Nenhum vídeo encontrado nesta pasta.")
            print("Coloque este executável na mesma pasta dos vídeos.")
            try:
                input("\nPressione ENTER para tentar novamente ou Ctrl+C para sair...")
            except (EOFError, KeyboardInterrupt):
                break
            continue

        print(f"\nVídeos encontrados ({len(videos)}):")
        for i, v in enumerate(videos):
            print(f"  {i+1}. {v}")
            
        print("\nEscolha o vídeo (número) ou 'q' para sair:")
        try:
            escolha_video = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if escolha_video.lower() == 'q':
            break
            
        try:
            if not escolha_video:
                continue
            idx = int(escolha_video) - 1
            if idx < 0 or idx >= len(videos):
                raise ValueError
            video_selecionado = videos[idx]
        except ValueError:
            print("Opção inválida.")
            try:
                input("ENTER para continuar...")
            except:
                pass
            continue

        limpar_tela()
        print(f"Vídeo selecionado: {video_selecionado}")
        print("---------------------------------------")
        print("O que você deseja fazer?")
        print("1. ✂️  Remover Silêncio (Jumpcut Inteligente)")
        print("2. 📝 Gerar Legendas (Auto Caption + Correção IA)")
        print("3. 🚀 Processo Completo (Corte + Legenda + IA)")
        print("0. 🔙 Voltar")
        
        try:
            acao = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        try:
            if acao == '1':
                print("\nCarregando módulos de IA... aguarde...")
                from remove_silence import remover_silencio

                print("\nQual método de corte?")
                print("1. Inteligente (Fala/Whisper) [Padrão]")
                print("2. Volume (dB)")
                metodo_in = input(">>> ").strip()
                metodo = "volume" if metodo_in == '2' else "speech"
                
                base, ext = os.path.splitext(video_selecionado)
                output_path = f"{base}_cut{ext}"
                
                remover_silencio(video_selecionado, output_path, method=metodo)
                print(f"\n✅ Concluído! Salvo em: {output_path}")
                input("\nPressione ENTER para continuar...")

            elif acao == '2':
                print("\nCarregando módulos de IA... aguarde...")
                from auto_caption import processar_legenda_completo

                gemini_key = perguntar_gemini_key()

                print("\nDeseja personalizar o modelo? (Enter para 'small')")
                modelo = input("Modelo (tiny, base, small, medium, large): ").strip() or "small"
                
                base, ext = os.path.splitext(video_selecionado)
                output_path = f"{base}_legendado{ext}"
                
                processar_legenda_completo(
                    video_selecionado, 
                    output_path, 
                    model_name=modelo, 
                    language="pt", 
                    gemini_key=gemini_key
                )
                
                print(f"\n✅ Concluído! Salvo em: {output_path}")
                input("\nPressione ENTER para continuar...")

            elif acao == '3':
                print("\nCarregando módulos de IA... aguarde...")
                from remove_silence import remover_silencio
                from auto_caption import processar_legenda_completo

                gemini_key = perguntar_gemini_key()

                print("\nUsando configurações padrão...")
                base, ext = os.path.splitext(video_selecionado)
                
                # 1. Corte
                cut_path = f"{base}_cut{ext}"
                sucesso = remover_silencio(video_selecionado, cut_path, method="speech")
                
                video_to_caption = cut_path if sucesso else video_selecionado
                
                # 2. Legenda (Pipeline completo com correção)
                final_path = f"{base}_final{ext}"
                
                processar_legenda_completo(
                    video_to_caption, 
                    final_path, 
                    model_name="small", 
                    language="pt", 
                    gemini_key=gemini_key
                )
                
                print(f"\n✅ Processo Completo! Salvo em: {final_path}")
                input("\nPressione ENTER para continuar...")

            elif acao == '0':
                continue
            else:
                print("Opção inválida.")
        
        except Exception as e:
            print(f"\n❌ Erro: {e}")
            input("\nPressione ENTER para continuar...")

if __name__ == "__main__":
    main()
