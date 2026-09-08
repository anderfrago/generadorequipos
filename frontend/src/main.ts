import { Component, inject, signal } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideRouter, RouterLink, RouterOutlet, Routes } from '@angular/router';
import { Api } from './app/api';
import { TeacherPage } from './app/teacher';
import { StudentPage } from './app/student';

@Component({selector: 'app-home', imports: [RouterLink], template: `
  <section class="welcome">
    <span class="eyebrow">APRENDER A TRABAJAR JUNTOS</span>
    <h1>Distintas maneras de aportar.<br><em>Mejores equipos.</em></h1>
    <p class="lead">Conoce cómo trabajas, descubre qué puedes aportar y encuentra nuevas formas de colaborar en el aula.</p>
    <div class="row g-4 mt-4">
      <div class="col-md-6"><div class="card h-100 p-4"><span class="step">01 / ALUMNADO</span><h2 class="h4 mt-3">Tu forma de trabajar</h2><p>Para responder al cuestionario, abre el enlace individual que te ha facilitado tu docente.</p><p class="small text-secondary mb-0">No hay respuestas correctas o incorrectas. No es una calificación.</p></div></div>
      <div class="col-md-6"><div class="card h-100 p-4 teacher-card"><span class="step">02 / PROFESORADO</span><h2 class="h4 mt-3">Organiza tu aula</h2><p>Gestiona clases, revisa respuestas y prepara equipos con aportaciones complementarias.</p><a routerLink="/teacher" class="btn btn-primary align-self-start">Entrar al panel docente →</a></div></div>
    </div>
  </section>`})
class HomePage {}

@Component({selector: 'app-root', imports: [RouterLink, RouterOutlet], template: `
  <header class="topbar"><div class="container d-flex align-items-center justify-content-between gap-3"><a routerLink="/" class="brand"><img class="brand-logo" src="https://cuatrovientos.org/wp-content/uploads/2025/01/LOGO-CENTRO-INTEGRADO-CUATROVIENTOS-300x115-2.png" alt="Centro Integrado Cuatrovientos" width="300" height="115"><span class="brand-title">Equipos equilibrados</span></a><nav class="d-flex align-items-center gap-3"><a routerLink="/teacher">Panel docente</a>@if(api.user(); as user){<span class="small d-none d-md-inline">{{user.name}}</span><button class="btn btn-sm btn-outline-secondary" (click)="logout()">Salir</button>}</nav></div></header>
  <main class="container py-4 py-lg-5">@if(error()){<div class="alert alert-danger" role="alert">{{error()}}</div>}@if(ready()){<router-outlet/>}@else{<p role="status">Cargando…</p>}</main>
  <footer class="container py-4 small text-secondary">Una herramienta para orientar la observación y el trabajo en equipo.</footer>`})
class App {
  api = inject(Api); ready = signal(false); error = signal('');
  constructor() { this.api.session().then(() => this.ready.set(true)).catch(e => this.error.set(e.message)); }
  async logout() { await this.api.request('/logout', 'POST', {}); location.assign('/'); }
}
const routes: Routes = [{path: '', component: HomePage}, {path: 'teacher', component: TeacherPage}, {path: 'student', component: StudentPage}, {path: '**', redirectTo: ''}];
bootstrapApplication(App, {providers: [provideRouter(routes)]}).catch(console.error);
