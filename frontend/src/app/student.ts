import { Component, inject, signal, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';

@Component({selector: 'app-student', imports: [FormsModule], template: `
  @if(error()){<div class="alert alert-danger" role="alert">{{error()}}</div>}
  @if(data(); as d){<section class="questionnaire mx-auto"><span class="eyebrow">{{d.className}}</span><h1 class="mt-2">Hola, {{d.student}}.</h1>
    @if(!submission()?.confirmed){<div class="card p-4 mt-4"><h2 class="h4">¿Cómo tiendo a funcionar y trabajar?</h2><p>Responde pensando en cómo sueles trabajar normalmente. No hay respuestas correctas o incorrectas y el resultado no es una calificación.</p><p>Tu docente podrá consultar tus respuestas para acompañar el trabajo en el aula y preparar equipos. Este enlace es personal: no lo compartas.</p><label class="form-check mb-4"><input class="form-check-input" type="checkbox" [(ngModel)]="confirmed"><span class="form-check-label">He leído la información y quiero empezar.</span></label><button class="btn btn-primary align-self-start" [disabled]="!confirmed || busy()" (click)="start()">Empezar cuestionario →</button></div>}
    @else if(submission()?.status==='SUBMITTED'){<div class="card p-4 mt-4"><span class="badge text-bg-success align-self-start mb-3">Cuestionario enviado</span><h2 class="h4">{{submission().result.feedback.heading}}</h2><p>{{submission().result.feedback.explanation}}</p><div class="row g-3 my-2">@for(k of ['IMP','ORG','EXP','INT'];track k){<div class="col-6 col-md-3"><div class="profile-value"><strong>{{submission().result.feedback.scores[k]}} %</strong><span>{{labels[k]}}</span></div></div>}</div><h3 class="h5 mt-3">Lo que puedes aportar</h3>@for(text of submission().result.feedback.strengths;track text){<p>{{text}}</p>}<h3 class="h5 mt-3">Un próximo paso</h3><p>{{submission().result.feedback.nextStep}}</p><p class="small text-secondary mb-0">{{submission().result.feedback.reminder}}</p></div>}
    @else {<p class="lead">Piensa en lo habitual, no en lo que crees que se espera de ti.</p><div class="progress-panel"><div class="d-flex justify-content-between small mb-2"><span>{{answered()}} de {{d.questionnaire.items.length}} respuestas</span><span role="status">{{saveMessage()}}</span></div><div class="progress" role="progressbar" [attr.aria-valuenow]="answered()" aria-valuemin="0" [attr.aria-valuemax]="d.questionnaire.items.length"><div class="progress-bar" [style.width.%]="answered()/d.questionnaire.items.length*100"></div></div></div>
      <fieldset [disabled]="busy()" class="border-0 p-0 m-0 w-100">
      @for(item of d.questionnaire.items;track item.id){<fieldset class="question card p-4 my-3"><legend><span class="question-number">{{item.number}}</span>{{item.text}}</legend><div class="row g-2">@for(label of d.questionnaire.scale;track $index;let v=$index){<div class="col-6 col-md-3"><input class="btn-check" type="radio" [id]="'q'+item.id+'v'+v" [name]="'q'+item.id" [value]="v" [(ngModel)]="answers[item.id]" (ngModelChange)="changed()"><label class="btn btn-outline-secondary w-100 h-100 scale-option" [for]="'q'+item.id+'v'+v">{{label}}</label></div>}</div></fieldset>}
      <section class="card p-4 my-3"><h2 class="h4">¿Qué condiciones te ayudan a trabajar?</h2><p class="text-secondary">Puedes elegir varias. «Ninguna» es una opción exclusiva.</p>@for(c of d.questionnaire.conditions;track c.code){<label class="form-check my-2"><input class="form-check-input" type="checkbox" [checked]="conditions.includes(c.code)" (change)="toggle(c.code)"><span class="form-check-label">{{c.text}}</span></label>}@if(conditions.includes('OTHER')){<label class="mt-3">Otra condición<textarea class="form-control" [(ngModel)]="other" (ngModelChange)="changed()" maxlength="500"></textarea></label>}<label class="mt-4">¿Qué te gustaría que tu equipo supiera para trabajar mejor contigo?<textarea class="form-control mt-2" rows="4" [(ngModel)]="openResponse" (ngModelChange)="changed()" maxlength="2000"></textarea></label></section>
      <div class="d-flex gap-3 justify-content-end my-4"><button class="btn btn-outline-primary" (click)="save(false)">Guardar y continuar después</button><button class="btn btn-primary" [disabled]="answered()!==d.questionnaire.items.length" (click)="save(true)">Enviar cuestionario →</button></div>
      </fieldset>
    }
  </section>} @else if(!error()){<p role="status">Abriendo tu cuestionario…</p>}
`})
export class StudentPage implements OnDestroy {
  api=inject(Api); data=signal<any>(null); submission=signal<any>(null); busy=signal(false); error=signal(''); saveMessage=signal('');
  confirmed=false; answers:Record<string,number>={}; conditions:string[]=[]; other=''; openResponse=''; labels:Record<string,string>={IMP:'Impulsar',ORG:'Organizar',EXP:'Explorar',INT:'Integrar'};
  private code=''; private token=''; private timer:ReturnType<typeof setTimeout>|undefined; private dirty=false; private saving=false;
  constructor(){const fragment=new URLSearchParams(location.hash.slice(1)); this.code=fragment.get('code')||''; this.token=fragment.get('token')||''; if(!this.code||!this.token){this.error.set('Abre el enlace individual que te ha facilitado tu docente.'); return;} void this.load();}
  async req(path:string,body?:unknown){const response=await fetch('/api/student'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':this.api.csrf,'X-Class-Code':this.code,'X-Student-Token':this.token},body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw new Error(result.error||'No se pudo guardar.');return result;}
  async load(){try{const d=await this.req('');this.data.set(d);if(d.submission)this.hydrate(d.submission);}catch(e){this.error.set((e as Error).message);}}
  hydrate(s:any){this.submission.set(s);this.answers={...s.answers};this.conditions=[...s.conditions];this.other=s.other_condition;this.openResponse=s.open_response;}
  async start(){this.busy.set(true);try{this.hydrate(await this.req('/start',{confirmed:this.confirmed}));}catch(e){this.error.set((e as Error).message);}finally{this.busy.set(false);}}
  answered(){return Object.keys(this.answers).length;}
  changed(){this.dirty=true;this.saveMessage.set('Cambios sin guardar');clearTimeout(this.timer);this.timer=setTimeout(()=>void this.save(false,true),20000);}
  toggle(code:string){if(this.conditions.includes(code))this.conditions=this.conditions.filter(c=>c!==code);else if(code==='NONE')this.conditions=['NONE'];else this.conditions=[...this.conditions.filter(c=>c!=='NONE'),code];this.changed();}
  async save(submit:boolean,automatic=false){
    if(this.saving || this.submission()?.status==='SUBMITTED')return;
    this.saving=true;this.busy.set(true);clearTimeout(this.timer);this.error.set('');
    try{const result=await this.req(submit?'/submit':'/save',{id:this.submission().id,answers:this.answers,conditions:this.conditions,other_condition:this.other,open_response:this.openResponse});this.submission.set(result);this.dirty=false;this.saveMessage.set(submit?'Enviado':'Guardado');if(submit)window.scrollTo({top:0,behavior:'smooth'});}
    catch(e){this.error.set((e as Error).message);this.saveMessage.set('No se ha guardado. Vuelve a intentarlo.');}
    finally{this.saving=false;this.busy.set(false);}
  }
  private beforeUnload=(event:BeforeUnloadEvent)=>{if(this.dirty){event.preventDefault();event.returnValue='';}};
  ngOnInit(){window.addEventListener('beforeunload',this.beforeUnload);}
  ngOnDestroy(){clearTimeout(this.timer);window.removeEventListener('beforeunload',this.beforeUnload);}
}
