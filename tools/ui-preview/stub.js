(function(){
const ok = d => Promise.resolve({ok:true, data:d});
const shows = [
 {id:"s1",name:"Fictional Studio",type:"youtube",feed_url:"x",auto:false,auto_train:false,folder:"unsorted",added_at:"2026-09-05T00:00:00+00:00"},
 {id:"s2",name:"Example Radio",type:"rss",feed_url:"y",auto:true,auto_train:false,folder:"unsorted",added_at:"2026-09-05T00:00:00+00:00"}];
const eps = [
 {id:"e1",title:"A fictional morning walk",url:"u1",kind:"mp3",date:"2026-08-12",duration:1417,show_id:"s2",show_name:"Example Radio"},
 {id:"e2",title:"An imaginary garden project",url:"u2",kind:"mp3",date:"2026-08-11",duration:1894,show_id:"s2",show_name:"Example Radio"},
 {id:"e3",title:"A fictional conversation about making things",url:"u3",kind:"youtube",date:"2026-01-31",show_id:"s1",show_name:"Fictional Studio"},
 {id:"e4",title:"Example episode with unavailable captions",url:"u4",kind:"youtube",date:"2026-01-13",show_id:"s1",show_name:"Fictional Studio"},
 {id:"e5",title:"The imaginary weekend",url:"u5",kind:"mp3",date:"2026-08-10",duration:1650,show_id:"s2",show_name:"Example Radio"}];
const jobs = {e2:{id:"e2",status:"transcribing",progress:0.42,title:eps[1].title,show_id:"s2",show_name:"Example Radio",url:"u2",kind:"mp3"},
              e4:{id:"e4",status:"failed",error:"No captions on this video",title:eps[3].title,show_id:"s1",show_name:"Fictional Studio",url:"u4",kind:"youtube"},
              e5:{id:"e5",status:"cancelled",title:eps[4].title,show_id:"s2",show_name:"Example Radio",url:"u5",kind:"mp3"}};
const known = {
 list_shows:()=>ok(shows), list_folders:()=>ok([]), get_settings:()=>ok({model:"base.en",device:"cpu",lang:"en",transcripts_dir:null,deck_theme:"studio"}),
 get_training_settings:()=>ok({has_api_key:false,api_key_last4:null,deck_theme:"studio",themes:{studio:"studio"}}),
 check_shows:()=>ok({episodes:eps,errors:[],checked_at:"2026-09-05T18:00:00+00:00",show_count:2}),
 job_states:()=>ok({jobs:jobs,pending:0}), train_job_states:()=>ok({jobs:{},pending:0}),
 app_info:()=>ok({version:"3.1",frozen:false,state_dir:"C:/Users/you/Sori",transcripts_dir:"C:/Users/you/Sori/Transcripts"}),
 list_transcripts:()=>ok([]), list_trainings:()=>ok([]),
 dismiss_episode:(s,i)=>ok({id:i,status:"dismissed"}), dismiss_episodes:(items)=>ok({dismissed:items.length}),
 transcribe_episode:(s,e)=>ok({id:e.id,status:"queued"}), stop_episode:(i)=>ok({id:i,status:"cancelling"}),
};
window.pywebview = { api: new Proxy({}, { get:(t,m)=> (m==="then"||typeof m==="symbol") ? undefined : (known[m] || (()=>ok({}))) }) };
})();
